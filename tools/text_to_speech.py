"""Mac-side text-to-speech for spoken replies, behind one interface.

A speaker has a `name` and `stream(text, stop)`: an async iterator of 24 kHz
mono s16le chunks that ends early once the asyncio.Event `stop` is set. The
service passes it the host-checked text (ADR-0012) through `spoken_form`, which
spells out decimals and unit symbols. The default is local Pocket
TTS with the voice "alba" (the user's pick); macOS `say` is the fallback.
Importing this module loads no model; tests use fakes.
"""
import asyncio
from pathlib import Path
import subprocess
import tempfile
import threading
import wave

import re

DEFAULT_ENGINE = 'pocket'
ENGINES = ('pocket', 'say', 'none')
POCKET_VOICE = 'alba'
SAY_VOICE = 'Samantha'
RATE_HZ = 24000


# Pocket TTS stumbles on decimals and unit symbols, so the voice gets them as words.
# The screen keeps the checked text; only the spoken copy changes.
UNITS = {
    'mAh': 'milliamp hour', 'mWh': 'milliwatt hour', 'mA': 'milliamp', 'mW': 'milliwatt',
    'kHz': 'kilohertz', 'Hz': 'hertz', 'dB': 'decibel', 'ms': 'millisecond', 'mg': 'milli g',
    'V': 'volt', 'W': 'watt', 'A': 'amp', 'g': 'g', 's': 'second', '%': 'percent', '°': 'degree',
}
UNCOUNTED = {'kilohertz', 'hertz', 'percent', 'g', 'milli g'}
DIGITS = 'zero one two three four five six seven eight nine'.split()
_UNIT = '|'.join(re.escape(unit) for unit in sorted(UNITS, key=len, reverse=True))
_CLOCK = re.compile(r'(?<![\w:.])(\d{1,2}):(\d\d)(?![\w:])')
_NUMBER = re.compile(r'(?<![\w.])(-?)(\d+)(?:\.(\d+))?(?:\s?(' + _UNIT + r')(?![\w]))?')
_BARE_UNIT = re.compile(r'(?<![\w.])(mAh|mWh|mA|mW|kHz|Hz|dB)(?!\w)')


def _unit_words(unit, singular):
    words = UNITS[unit]
    return words if singular or words in UNCOUNTED else words + 's'


def _clock(match):
    minutes, seconds = int(match.group(1)), int(match.group(2))
    parts = [f'{minutes} minute{"" if minutes == 1 else "s"}'] if minutes else []
    if seconds or not minutes:
        parts.append(f'{seconds} second{"" if seconds == 1 else "s"}')
    return ' '.join(parts)


def _number(match):
    sign, whole, fraction, unit = match.groups()
    fraction = (fraction or '').rstrip('0')
    words = ('minus ' if sign else '') + ('zero' if fraction and whole == '0' else whole)
    if fraction:
        words += ' point ' + ' '.join(DIGITS[int(digit)] for digit in fraction)
    if unit:
        words += ' ' + _unit_words(unit, singular=whole == '1' and not fraction)
    return words


def spoken_form(text):
    """The text as the voice should read it: 7.2 dB becomes "7 point two decibels"."""
    text = _CLOCK.sub(_clock, text)
    text = _NUMBER.sub(_number, text)
    return _BARE_UNIT.sub(lambda match: _unit_words(match.group(1), singular=False), text)


class PocketSpeaker:
    """Pocket TTS on one dedicated thread (the model is not thread-safe); chunks
    reach the event loop as they are generated, about 11x faster than real time."""

    def __init__(self, voice=POCKET_VOICE):
        self.name = f'pocket-tts:{voice}'
        self.voice = voice
        self._lock = threading.Lock()
        self._model = self._state = None

    def load(self):
        from pocket_tts import TTSModel
        with self._lock:
            self._model = TTSModel.load_model()
            if self._model.sample_rate != RATE_HZ:
                raise RuntimeError('unexpected Pocket TTS sample rate')
            self._state = self._model.get_state_for_audio_prompt(self.voice)

    async def stream(self, text, stop):
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        halt = threading.Event()
        def generate():
            try:
                import torch
                with self._lock:
                    for chunk in self._model.generate_audio_stream(self._state, text, stop=halt):
                        pcm = (chunk.clamp(-1, 1) * 32767).round().to(torch.int16).numpy().tobytes()
                        loop.call_soon_threadsafe(queue.put_nowait, pcm)
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except Exception as error:  # surfaces in the service as a failed stream
                loop.call_soon_threadsafe(queue.put_nowait, error)
        thread = threading.Thread(target=generate, name='tts', daemon=True)
        thread.start()
        try:
            while True:
                getter = asyncio.ensure_future(queue.get())
                stopper = asyncio.ensure_future(stop.wait())
                done, _ = await asyncio.wait({getter, stopper}, return_when=asyncio.FIRST_COMPLETED)
                if getter not in done:
                    getter.cancel()
                    return
                stopper.cancel()
                item = getter.result()
                if item is None:
                    return
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            halt.set()


class SaySpeaker:
    """macOS `say`: renders the whole text first (fast), then yields it in chunks."""

    def __init__(self, voice=SAY_VOICE):
        self.name = f'macos-say:{voice}'
        self.voice = voice

    def _render(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'speech.wav'
            subprocess.run(['say', '-v', self.voice, '-o', str(path), f'--data-format=LEI16@{RATE_HZ}', text],
                           check=True, capture_output=True, timeout=30)
            with wave.open(str(path)) as stream:
                if stream.getframerate() != RATE_HZ or stream.getnchannels() != 1 or stream.getsampwidth() != 2:
                    raise RuntimeError('unexpected say output format')
                return stream.readframes(stream.getnframes())

    async def stream(self, text, stop):
        audio = await asyncio.to_thread(self._render, text)
        for offset in range(0, len(audio), 9600):
            if stop.is_set():
                return
            yield audio[offset:offset + 9600]
            await asyncio.sleep(0)


def load_speaker(engine):
    if engine == 'none':
        return None
    if engine == 'pocket':
        speaker = PocketSpeaker()
        speaker.load()
        return speaker
    if engine == 'say':
        return SaySpeaker()
    raise ValueError(f'unknown text-to-speech engine {engine!r}; choose from {ENGINES}')
