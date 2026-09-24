"""Spoken ask (G-0002.01 Open 1): question audio, speech-to-noise and operator question."""
import hashlib
import math
import random
import struct
import sys
import unittest

from tools.investigation import (Investigation, MockProvider, ProtocolError, QuestionAudio,
                                 speech_to_noise, validate_request)
from test_investigation import captured, fixture


def question(identity='session-q1', samples=None, **changes):
    if samples is None:
        samples = speech(snr_db=15)
    raw = struct.pack(f'<{len(samples)}h', *samples)
    meta = dict(question_id=identity, boot_id='boot', session_id='session', format='pcm_s16le',
                sample_rate_hz=16000, channels=1, frames=len(samples), size_bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(), source_rate_hz=48000, source_slot=0,
                gain_db=24, filter='hpf80-lpf6500-63tap-decimate3', warmup_frames=12000,
                acquisition_start_us=1000, acquisition_end_us=3001000, stopped_by='operator',
                input_clipped=0, driver_epoch_integrity=True)
    meta.update(changes)
    return meta, raw


def speech(snr_db, seconds=3.0, onset=0.6, length=1.5, noise=300, duty=None, seed=1):
    """Uniform noise plus a 440 Hz burst whose power is snr_db above the noise power."""
    rng = random.Random(seed)
    noise_power = noise * noise / 3  # uniform on [-noise, noise]
    amplitude = math.sqrt(2 * noise_power * 10 ** (snr_db / 10))
    out = []
    for n in range(int(seconds * 16000)):
        t = n / 16000
        on = onset <= t < onset + length
        if on and duty:
            on = (t - onset) % 0.3 < 0.3 * duty
        value = rng.uniform(-noise, noise) + (amplitude * math.sin(2 * math.pi * 440 * t) if on else 0)
        out.append(max(-32768, min(32767, round(value))))
    return out


class QuestionAudioTests(unittest.TestCase):
    def test_valid_question_is_mono_16k_and_carries_its_own_identity(self):
        item = QuestionAudio.from_pcm(*question())
        self.assertEqual(item.metadata['question_id'], 'session-q1')
        self.assertEqual(item.analysis['frames'], 48000)
        self.assertAlmostEqual(item.analysis['duration_s'], 3.0)

    def test_rejects_wrong_format_extent_digest_and_fields(self):
        for change in ({'sample_rate_hz': 48000}, {'channels': 4}, {'frames': 128001},
                       {'size_bytes': 10}, {'sha256': '0' * 64}, {'format': 'f32'},
                       {'stopped_by': 'remote'}, {'driver_epoch_integrity': False},
                       {'question_id': '../x'}, {'acquisition_end_us': 1000},
                       {'input_clipped': -1}, {'extra': 1}, {'gain_db': True}):
            with self.subTest(change=change), self.assertRaises(ProtocolError):
                QuestionAudio.from_pcm(*question(**change))
        meta, raw = question()
        with self.assertRaises(ProtocolError):
            QuestionAudio.from_pcm(meta, raw[:-2])
        del meta['filter']
        with self.assertRaises(ProtocolError):
            QuestionAudio.from_pcm(meta, raw)

    def test_eight_second_limit_is_accepted(self):
        samples = [0] * 128000
        QuestionAudio.from_pcm(*question(samples=samples, stopped_by='limit'))


class SpeechToNoiseTests(unittest.TestCase):
    def test_stationary_burst_matches_constructed_level(self):
        for snr in (10, 20):
            with self.subTest(snr=snr):
                result = speech_to_noise(speech(snr))
                self.assertAlmostEqual(result['speech_to_noise_db'], snr, delta=0.5)
                self.assertAlmostEqual(result['onset_s'], 0.6, delta=0.03)
                self.assertAlmostEqual(result['speech_s'], 1.5, delta=0.05)

    def test_pauses_inside_the_utterance_count_as_speech_time(self):
        # On-level 12 dB for 2/3 of the span: mean speech power is 12 dB + 10log10(2/3).
        result = speech_to_noise(speech(12, duty=2 / 3))
        expected = 12 + 10 * math.log10(2 / 3)
        self.assertAlmostEqual(result['speech_to_noise_db'], expected, delta=0.7)

    def test_no_speech_or_digital_silence_has_no_level(self):
        self.assertIsNone(speech_to_noise(speech(0, length=0))['speech_to_noise_db'])
        silent = speech_to_noise([0] * 16000)
        self.assertIsNone(silent['speech_to_noise_db'])
        self.assertIsNone(silent['noise_dbfs'])

    def test_too_short_to_hold_a_noise_window(self):
        result = speech_to_noise([100] * 3000)
        self.assertIsNone(result['speech_to_noise_db'])

    def test_counts_clipping_and_peak(self):
        samples = speech(10)
        samples[5000] = 32767
        result = speech_to_noise(samples)
        self.assertEqual(result['clipped_samples'], 1)
        self.assertEqual(result['peak_counts'], 32767)


class OperatorQuestionTests(unittest.TestCase):
    def test_confirmed_question_reaches_requests_as_operator_context(self):
        flow = Investigation('boot', 'session', fixture())
        flow.ask()
        flow.question('Is the fan louder near the wall?')
        flow.start_capture()
        request = flow.finish_capture(captured())
        self.assertEqual(request['operator_question'], 'Is the fan louder near the wall?')
        self.assertEqual(request['fixture'], fixture().to_dict())
        reply = MockProvider().respond(request)
        self.assertIn('Is the fan louder near the wall?', reply['text'])

    def test_question_only_before_record_a_and_bounded(self):
        flow = Investigation('boot', 'session', fixture())
        with self.assertRaises(ProtocolError):
            flow.question('Too early')
        flow.ask()
        for bad in ('', ' ', 'x' * 513, None):
            with self.subTest(bad=bad), self.assertRaises(ProtocolError):
                flow.question(bad)
        flow.start_capture()
        with self.assertRaises(ProtocolError):
            flow.question('Too late')

    def test_request_without_question_stays_valid_and_bad_question_rejected(self):
        flow = Investigation('boot', 'session', fixture())
        flow.ask(); flow.start_capture()
        request = flow.finish_capture(captured())
        self.assertIsNone(request['operator_question'])
        validate_request(request)
        for bad in (7, '', 'x' * 513):
            with self.subTest(bad=bad), self.assertRaises(ProtocolError):
                validate_request({**request, 'operator_question': bad})


class TranscriberSeamTests(unittest.TestCase):
    def test_importing_the_seam_does_not_load_parakeet_or_mlx(self):
        import tools.speech_to_text as stt
        self.assertNotIn('parakeet_mlx', sys.modules)
        self.assertNotIn('mlx', sys.modules)
        self.assertEqual(stt.DEFAULT_ENGINE, 'parakeet')
        self.assertIsNone(stt.load_transcriber('none'))
        with self.assertRaises(ValueError):
            stt.load_transcriber('cloud-without-adapter')


if __name__ == '__main__':
    unittest.main()
