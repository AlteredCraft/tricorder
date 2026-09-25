"""Contract checks written before the G-0002 mock/state implementation."""
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

from tools.investigation import (CaptureEvidence, Fixture, Investigation, MockProvider,
                                 ProtocolError, RunArchive, device_text, validate_reply)


def evidence(identity='take-a', amplitude=1000, **changes):
    raw = struct.pack('<hhhh', amplitude, 12, -45, 0) * 480
    raw += struct.pack('<hhhh', -amplitude, 12, -45, 0) * 480
    meta = dict(status='complete', boot_id='boot', session_id='session', capture_id=identity,
                format='pcm_s16le', sample_rate_hz=48000, channels=4, frames=960, gain_db=24,
                source_slot=0, physical_slot='farther-hole', speaker_active=False,
                driver_epoch_integrity=True, acquisition_start_us=100, acquisition_end_us=20100,
                size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    meta.update(changes)
    return meta, raw


def fixture():
    return Fixture(question='How does recorded fan sound change with distance?',
                   variable='distance', placement_a='20 cm; same orientation',
                   placement_b='40 cm; same orientation', expected='B has lower digital RMS',
                   sample_rate_hz=48000, frames=960, channels=4, gain_db=24,
                   source_slot=0, physical_slot='farther-hole')


def captured(identity='take-a', amplitude=1000, **changes):
    return CaptureEvidence.from_pcm(*evidence(identity, amplitude, **changes))


class EvidenceTests(unittest.TestCase):
    def test_measurements_are_computed_from_selected_raw_slot(self):
        item = captured()
        self.assertEqual(item.measurement['rms_counts'], 1000)
        self.assertEqual(item.measurement['peak_counts'], 1000)
        self.assertEqual(item.measurement['clipped_samples'], 0)
        self.assertAlmostEqual(item.measurement['rms_dbfs'], 20 * math.log10(1000 / 32768))
        self.assertEqual(item.measurement['frames'], 960)

    def test_rejects_incomplete_corrupt_missing_and_playback_evidence(self):
        for change in ({'status':'incomplete'}, {'sha256':'0'*64}, {'frames':959},
                       {'source_slot':4}, {'source_slot':True}, {'driver_epoch_integrity':False},
                       {'speaker_active':True}, {'physical_slot':''}, {'gain_db':float('nan')},
                       {'capture_id':'../escape'}, {'session_id':''}):
            with self.subTest(change=change), self.assertRaises(ProtocolError):
                captured(**change)
        meta, raw = evidence()
        with self.assertRaises(ProtocolError): CaptureEvidence.from_pcm(meta, raw[:-8])

    def test_silence_has_no_infinite_json_values(self):
        item = captured(amplitude=0)
        self.assertIsNone(item.measurement['rms_dbfs'])
        json.dumps(item.to_dict(), allow_nan=False)

    def test_mutating_callers_metadata_does_not_change_retained_evidence(self):
        meta, raw = evidence()
        item = CaptureEvidence.from_pcm(meta, raw)
        meta['gain_db'] = 90
        exported = item.to_dict(); exported['settings']['gain_db'] = 99
        self.assertEqual(item.to_dict()['settings']['gain_db'], 24)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.flow = Investigation('boot', 'session', fixture(), clock=lambda:self.now)
        self.provider = MockProvider()

    def start_a(self):
        self.flow.ask()
        self.assertEqual(self.flow.state, 'ready_a')
        self.flow.start_capture()
        self.assertEqual(self.flow.state, 'recording_a')
        return self.flow.finish_capture(captured())

    def guidance(self):
        request = self.start_a()
        reply = self.provider.respond(request)
        self.flow.accept(reply)
        return request, reply

    def test_complete_sequence_joins_actual_measurements_and_adjustment(self):
        request, reply = self.guidance()
        self.assertEqual(self.flow.state, 'adjust')
        self.assertEqual(reply['capture_ids'], ['take-a'])
        self.assertEqual(reply['measurements'][0]['rms_counts'], 1000)
        self.flow.adjust('Moved from 20 cm to 40 cm; orientation unchanged')
        self.flow.start_capture()
        request = self.flow.finish_capture(captured('take-b', 500, acquisition_start_us=30000,
                                                   acquisition_end_us=50000))
        self.assertEqual(self.flow.state, 'waiting')
        reply = self.provider.respond(request)
        ack = self.flow.accept(reply)
        self.assertEqual(ack['type'], 'ack')
        self.assertEqual(ack['request_id'], request['request_id'])
        self.assertEqual(self.flow.state, 'complete')
        self.assertEqual(self.flow.result['capture_ids'], ['take-a', 'take-b'])
        self.assertAlmostEqual(reply['comparison']['rms_delta_db'], -6.020599913)
        self.assertIn('40 cm', request['adjustment'])
        self.assertEqual([e['state'] for e in self.flow.transitions],
                         ['idle','ready_a','recording_a','waiting','adjust','ready_b',
                          'recording_b','waiting','complete'])

    def test_wrong_identity_unknown_capture_and_duplicate_reply_cannot_act(self):
        request = self.start_a(); reply = self.provider.respond(request)
        for change in ({'boot_id':'other'}, {'session_id':'old'}, {'request_id':'unknown'},
                       {'capture_ids':['missing']}, {'type':'request_capture'},
                       {'deadline_ms':request['deadline_ms'] + 1}, {'version':2}):
            with self.subTest(change=change), self.assertRaises(ProtocolError):
                self.flow.accept({**reply, **change})
            self.assertEqual(self.flow.state, 'waiting')
        self.flow.accept(reply)
        with self.assertRaises(ProtocolError): self.flow.accept(reply)
        self.assertEqual(self.flow.state, 'adjust')

    def test_delayed_cancelled_disconnected_and_expired_responses(self):
        request = self.start_a(); reply = self.provider.respond(request)
        self.now += 5000
        self.assertEqual(self.flow.state, 'waiting')
        self.flow.cancel()
        with self.assertRaises(ProtocolError): self.flow.accept(reply)
        self.assertEqual(self.flow.state, 'cancelled')
        for terminal in ('disconnect','expire'):
            with self.subTest(terminal=terminal):
                flow = Investigation('boot','new',fixture(),clock=lambda:self.now)
                flow.ask();flow.start_capture()
                request = flow.finish_capture(captured(session_id='new'))
                reply = self.provider.respond(request)
                if terminal == 'disconnect': flow.disconnect()
                else: self.now = request['deadline_ms'];flow.tick()
                with self.assertRaises(ProtocolError):flow.accept(reply)
                self.assertEqual(flow.state, 'offline' if terminal=='disconnect' else 'incomplete')

    def test_settings_duplicate_capture_and_wrong_session_do_not_compare(self):
        self.guidance();self.flow.adjust('Moved to 40 cm');self.flow.start_capture()
        for change in ({'gain_db':30}, {'session_id':'old'}, {'boot_id':'other'},
                       {'capture_id':'take-a'}, {'source_slot':2}, {'physical_slot':'other'},
                       {'acquisition_start_us':99}):
            with self.subTest(change=change), self.assertRaises(ProtocolError):
                self.flow.finish_capture(captured('take-b', 500, **change))
        self.assertEqual(self.flow.state, 'recording_b')

    def test_pending_queue_and_capture_limits(self):
        self.start_a()
        with self.assertRaises(ProtocolError):self.flow.start_capture()
        with self.assertRaises(ProtocolError):self.flow.finish_capture(captured('extra'))
        self.assertEqual(len(self.flow.captures),1)
        self.flow.cancel()
        with self.assertRaises(ProtocolError):self.flow.ask()

    def test_cancel_while_recording_late_completion_and_bad_transitions(self):
        with self.assertRaises(ProtocolError):self.flow.start_capture()
        self.flow.ask();self.flow.start_capture();self.flow.cancel()
        with self.assertRaises(ProtocolError):self.flow.finish_capture(captured())
        self.assertEqual(len(self.flow.captures),0)

    def test_provider_contract_rejects_unbacked_measurements_and_claims(self):
        request = self.start_a(); reply = self.provider.respond(request)
        validate_reply(request, reply)
        for mutation in ('measurement','extra','text','comparison'):
            bad = copy.deepcopy(reply)
            if mutation=='measurement':bad['measurements'][0]['rms_counts']=1
            if mutation=='extra':bad['capture_ids'].append('invented')
            if mutation=='text':bad['text']='x'*2049
            if mutation=='comparison':bad['comparison']={'rms_delta_db':-6}
            with self.subTest(mutation=mutation),self.assertRaises(ProtocolError):
                validate_reply(request,bad)
        # The device font has ASCII glyphs only; anything else draws as a box.
        bad = copy.deepcopy(reply); bad['text'] = 'Changed by \u00b10.2 dB.'
        with self.assertRaises(ProtocolError):
            validate_reply(request, bad)

    def test_device_text_maps_model_punctuation_to_ascii(self):
        cases = {
            'the repeat changed by \u00b10.2 dB': 'the repeat changed by +/-0.2 dB',
            'repeat the full A\u2192B\u2192A check': 'repeat the full A to B to A check',
            'B/A was \u22126.0 dB': 'B/A was -6.0 dB',
            'A \u2013 B \u2014 then A': 'A - B - then A',
            'larger\u2014so repeat': 'larger - so repeat',
            '\u201cWhat\u2019s louder?\u201d': '"What\'s louder?"',
            'wait\u2026': 'wait...',
            'about\u00a012 inches': 'about 12 inches',
            'caf\u00e9 \u2248 \u2264 \u2265': 'cafe ~ <= >=',
            'plain \U0001f600 text': 'plain text',
        }
        for raw, shown in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(device_text(raw), shown)
                self.assertTrue(shown.isascii())

    def test_input_and_fixture_bounds(self):
        with self.assertRaises(ProtocolError):
            Investigation('boot','../bad',fixture())
        with self.assertRaises(ProtocolError):
            Fixture(**{**fixture().to_dict(), 'frames':48000*61})
        self.guidance()
        with self.assertRaises(ProtocolError):self.flow.adjust('')
        with self.assertRaises(ProtocolError):self.flow.adjust('x'*513)


class ArchiveTests(unittest.TestCase):
    def test_no_overwrite_capacity_and_readback_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'run'
            archive=RunArchive(root,'boot','session',fixture(),max_bytes=15360)
            archive.store(captured())
            with self.assertRaises(ProtocolError):archive.store(captured())
            archive.store(captured('take-b'))
            with self.assertRaises(ProtocolError):archive.store(captured('take-c'))
            self.assertEqual(archive.load('take-a').measurement['rms_counts'],1000)
            manifest=json.loads((root/'manifest.json').read_text())
            self.assertEqual(manifest['spec_id'],'G-0002.01')
            self.assertEqual(manifest['spec_revision'],'2026-09-21')
            with self.assertRaises(FileExistsError):RunArchive(root,'boot','session',fixture())
            (root/'captures/take-a.bin').write_bytes(b'bad')
            with self.assertRaises(ProtocolError):archive.load('take-a')

    def test_byte_limit_checked_before_writing_and_cross_session_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=RunArchive(Path(directory)/'run','boot','session',fixture(),max_bytes=7679)
            with self.assertRaises(ProtocolError):archive.store(captured())
            with self.assertRaises(ProtocolError):archive.store(captured(session_id='other'))
            self.assertEqual(list((archive.root/'captures').iterdir()),[])

    def test_transcript_capacity_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=RunArchive(Path(directory)/'run','boot','session',fixture(),max_events=2)
            archive.record({'type':'ask'});archive.record({'type':'cancel'})
            with self.assertRaises(ProtocolError):archive.record({'type':'ask'})
            self.assertEqual(len((archive.root/'transcript.jsonl').read_text().splitlines()),2)



class AdditionalIntegrityTests(unittest.TestCase):
    def test_reducer_rechecks_evidence_instead_of_trusting_object_measurements(self):
        meta,raw=evidence()
        forged=CaptureEvidence(meta,raw,{'rms_counts':42})
        flow=Investigation('boot','session',fixture())
        flow.ask();flow.start_capture()
        request=flow.finish_capture(forged)
        self.assertEqual(request['captures'][0]['measurement']['rms_counts'],1000)

    def test_reply_boolean_cannot_masquerade_as_numeric_measurement(self):
        flow=Investigation('boot','session',fixture())
        flow.ask();flow.start_capture()
        request=flow.finish_capture(captured(amplitude=0))
        reply=MockProvider().respond(request)
        reply['measurements'][0]['clipped_samples']=False
        with self.assertRaises(ProtocolError):validate_reply(request,reply)

    def test_long_session_id_still_generates_valid_request(self):
        flow=Investigation('boot','s'*96,fixture())
        flow.ask();flow.start_capture()
        request=flow.finish_capture(captured(session_id='s'*96))
        validate_reply(request,MockProvider().respond(request))

    def test_clipping_does_not_report_a_valid_ratio(self):
        flow=Investigation('boot','session',fixture())
        flow.ask();flow.start_capture()
        request=flow.finish_capture(captured(amplitude=32767))
        flow.accept(MockProvider().respond(request));flow.adjust('Moved to 40 cm');flow.start_capture()
        request=flow.finish_capture(captured('take-b',500,acquisition_start_us=30000,acquisition_end_us=50000))
        reply=MockProvider().respond(request)
        self.assertEqual(reply['comparison']['status'],'inconclusive')
        self.assertIsNone(reply['comparison']['rms_delta_db'])


if __name__ == '__main__':unittest.main()
