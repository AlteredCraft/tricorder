"""Shared rules for the Mac service: identities, bounded text, the voice note, the
number check on model prose (ADR-0012) and the private per-session archive.

Wire format: planning/service.md. The device's side is firmware/main/service_protocol.cpp.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time
import unicodedata

VERSION = 1
MAX_TEXT = 2048
# Voice note (ADR-0013): 16 kHz mono speech, at most 8 s, called a question on the wire.
QUESTION_RATE_HZ = 16000
MAX_QUESTION_FRAMES = QUESTION_RATE_HZ * 8
MAX_QUESTIONS = 5
MAX_QUESTION_TEXT = 512
QUESTION_FILTER = 'hpf80-lpf6500-63tap-decimate3'
QUESTION_FIELDS = {'question_id', 'boot_id', 'session_id', 'format', 'sample_rate_hz', 'channels',
                   'frames', 'size_bytes', 'sha256', 'source_rate_hz', 'source_slot', 'gain_db',
                   'filter', 'warmup_frames', 'acquisition_start_us', 'acquisition_end_us',
                   'stopped_by', 'input_clipped', 'driver_epoch_integrity'}


class ProtocolError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value),
            'invalid identity')
    return value


def bounded_text(value, limit):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit
            and len(value.encode('utf-8')) <= limit, 'text outside bounds')
    return value


# The device draws text with LVGL's built-in Montserrat, which has ASCII glyphs only.
_DEVICE_PUNCTUATION = str.maketrans({
    '\u00b1': '+/-', '\u2192': ' to ', '\u27f6': ' to ', '\u21d2': ' to ',
    '\u2212': '-', '\u2010': '-', '\u2011': '-', '\u2013': '-', '\u2014': ' - ',
    '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2026': '...',
    '\u00d7': 'x', '\u2248': '~', '\u2264': '<=', '\u2265': '>=', '\u00b0': ' degrees'})


def device_text(value):
    """Text the device font can draw: common model punctuation becomes ASCII,
    accents are dropped and any other character is removed."""
    text = unicodedata.normalize('NFKD', value.translate(_DEVICE_PUNCTUATION))
    text = text.encode('ascii', 'ignore').decode()
    return re.sub(r' {2,}', ' ', text).strip()


def integer(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, 'integer outside bounds')
    return value


def speech_to_noise(samples, rate=QUESTION_RATE_HZ):
    """Speech level over pre-speech noise in one question buffer (ADR-0013's watch number).

    Noise: mean power of the first 200 ms, before the person starts speaking.
    Utterance: first to last 20 ms frame at least 6 dB above that noise, so pauses
    between words count as speech time. Speech power is the utterance's mean power
    minus the noise power. None when the buffer is too short, silent or has no speech.
    """
    frame = rate // 50
    noise_frames = 10
    peak = max((abs(x) for x in samples), default=0)
    result = dict(frames=len(samples), duration_s=len(samples)/rate, peak_counts=peak,
                  clipped_samples=sum(x in (-32768, 32767) for x in samples),
                  noise_dbfs=None, speech_dbfs=None, speech_to_noise_db=None,
                  onset_s=None, speech_s=None)
    powers = [math.fsum(x*x for x in samples[i:i+frame])/frame
              for i in range(0, len(samples)-frame+1, frame)]
    if len(powers) <= noise_frames:
        return result
    noise = math.fsum(powers[:noise_frames])/noise_frames
    if not noise:
        return result
    result['noise_dbfs'] = 10*math.log10(noise/32768**2)
    active = [i for i in range(noise_frames, len(powers)) if powers[i] >= 4*noise]
    if not active:
        return result
    span = powers[active[0]:active[-1]+1]
    speech = math.fsum(span)/len(span)-noise
    result.update(onset_s=active[0]*frame/rate, speech_s=len(span)*frame/rate)
    if speech > 0:
        result.update(speech_dbfs=10*math.log10(speech/32768**2),
                      speech_to_noise_db=10*math.log10(speech/noise))
    return result


class QuestionAudio:
    """One voice note: 16 kHz mono speech derived on the device from microphone slot 0
    (ADR-0006, ADR-0013)."""
    def __init__(self, metadata, raw, samples):
        self._metadata = deepcopy(metadata)
        self.raw = bytes(raw)
        self.samples = samples
        self.analysis = speech_to_noise(samples)

    @classmethod
    def from_pcm(cls, metadata, raw):
        require(isinstance(metadata, dict) and set(metadata) == QUESTION_FIELDS, 'question metadata fields')
        meta = deepcopy(metadata)
        for key in ('question_id', 'boot_id', 'session_id'):
            identity(meta[key])
        require(meta['format'] == 'pcm_s16le' and meta['filter'] == QUESTION_FILTER, 'question format')
        integer(meta['sample_rate_hz'], QUESTION_RATE_HZ, QUESTION_RATE_HZ)
        integer(meta['channels'], 1, 1)
        integer(meta['source_rate_hz'], 48000, 48000)
        integer(meta['source_slot'], 0, 0)
        integer(meta['gain_db'], 0, 48)
        integer(meta['warmup_frames'], 0, 48000)
        integer(meta['input_clipped'], 0, 2**53-1)
        frames = integer(meta['frames'], 1, MAX_QUESTION_FRAMES)
        require(isinstance(raw, bytes) and len(raw) == frames*2 and type(meta['size_bytes']) is int
                and meta['size_bytes'] == len(raw), 'question byte extent mismatch')
        require(hashlib.sha256(raw).hexdigest() == meta['sha256'], 'question digest mismatch')
        require(meta['stopped_by'] in ('operator', 'limit'), 'question stop reason')
        require(meta['driver_epoch_integrity'] is True, 'question driver integrity missing')
        start = integer(meta['acquisition_start_us'], 0, 2**53-1)
        integer(meta['acquisition_end_us'], start+1, 2**53-1)
        return cls(meta, raw, list(struct.unpack(f'<{frames}h', raw)))

    @property
    def metadata(self):
        return deepcopy(self._metadata)


MEASURED_NUMBER = re.compile(r'([-+\u2212]?\d+(?:\.\d+)?)\s*(dBFS|dB|kHz|Hz|counts?)\b')
_UNIT_FAMILY = {'dBFS': 'db', 'dB': 'db', 'kHz': 'hz', 'Hz': 'hz', 'count': 'counts', 'counts': 'counts'}
_KEY_FAMILY = (('_dbfs', 'db'), ('_db', 'db'), ('_hz', 'hz'), ('_counts', 'counts'))


def _measured(match):
    """(unit family, value in base unit, precision in base unit) of one match."""
    token = match.group(1).replace('\u2212', '-').lstrip('+-')
    scale = 1000 if match.group(2) == 'kHz' else 1
    decimals = len(token.split('.')[1]) if '.' in token else 0
    return _UNIT_FAMILY[match.group(2)], float(token)*scale, 0.5*10**-decimals*scale+1e-9


def unbacked_numbers(text, evidence):
    """Numbers stated with a measurement unit that no host-supplied value supports.

    Allowed values come from the evidence sent to the model: numeric fields whose
    name carries the unit (background_db, tone_hz, ...) and unit-bearing numbers
    inside its strings.
    A stated value may be rounded to its precision; sign is ignored.
    """
    allowed = {'db': [], 'hz': [], 'counts': []}
    def collect(value, key=''):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            family = next((f for suffix, f in _KEY_FAMILY if key.endswith(suffix)), None)
            if family:
                allowed[family].append(abs(float(value)))
        elif isinstance(value, str):
            for match in MEASURED_NUMBER.finditer(value):
                family, number, _ = _measured(match)
                allowed[family].append(number)
        elif isinstance(value, dict):
            for name, item in value.items():
                collect(item, str(name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item, key)
    collect(evidence)
    unbacked = []
    for match in MEASURED_NUMBER.finditer(text):
        family, stated, tolerance = _measured(match)
        if not any(abs(stated-value) <= tolerance for value in allowed[family]):
            unbacked.append(match.group(0))
    return unbacked


class MockProvider:
    name = 'scripted-mock-v1'

    def explain(self, evidence):
        """Deterministic reading of a sound (F-0002), motion (F-0005), photo (F-0006) or power (F-0007) analysis."""
        from tools import camera_explain, motion_explain, power_explain, sound_explain
        module = {'motion': motion_explain, 'camera': camera_explain,
                  'power': power_explain}.get(evidence.get('kind'), sound_explain)
        return module.mock_text(evidence)


class RunArchive:
    """Exclusive private directory for one session: a manifest and a bounded transcript.

    A failed write poisons the archive. Never recycle a run directory.
    """
    def __init__(self, root, boot_id, session_id, *, max_events=256):
        self.boot_id, self.session_id = identity(boot_id), identity(session_id)
        self.max_events = integer(max_events, 1, 1024)
        self.events = 0
        self.failed = False
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False, mode=0o700)
        manifest = dict(protocol_version=VERSION, run_id=self.root.name, boot_id=boot_id, session_id=session_id,
                        created_utc=datetime.now(timezone.utc).isoformat(), max_transcript_events=max_events,
                        clocks='device times are device monotonic; host_receipt_ns is Mac monotonic; do not subtract')
        (self.root/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')

    def record(self, event):
        require(not self.failed and self.events<self.max_events, 'transcript capacity/archive failure')
        data = json.dumps({'host_receipt_ns':time.monotonic_ns(), 'message':event},allow_nan=False)
        require(len(data.encode())<=32768, 'transcript event size')
        try:
            with (self.root/'transcript.jsonl').open('a') as stream:stream.write(data+'\n')
        except Exception:
            self.failed = True
            raise
        self.events+=1
