import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from tools.capture_serial import main


class CaptureSerialTests(unittest.TestCase):
    def test_replay_validates_before_opening_port(self):
        with tempfile.TemporaryDirectory() as directory:
            for session,reset in [('bad',True),('ab-'+'a'*32,False)]:
                argv=['capture','--port','test','--output',directory+'/run','--replay-session',session,
                      '--spec-id','G-0002.01','--spec-revision','2026-09-22','--workload','SD replay']
                if reset:argv.append('--reset')
                with patch.object(sys,'argv',argv),self.assertRaises(SystemExit):main()
            self.assertFalse((Path(directory)/'run').exists())

    def test_replay_sends_once_after_current_boot_sd_and_network_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);stop=root/'stop';port=MagicMock();session='ab-'+'a'*32
            rows=[dict(event='boot'),dict(event='storage_ready',mounted=True),dict(event='wifi_address',ipv4='10.0.0.2'),
                  dict(event='check',check='storage_http',result='pass'),dict(event='wifi_address',ipv4='10.0.0.2'),
                  dict(event='investigation_state',state='complete',session_id=session)]
            chunks=[('TRICORDER '+json.dumps(dict(boot_id='boot',seq=i,device_us=i,**e))+'\n').encode() for i,e in enumerate(rows)]
            def read(_):
                if not chunks:stop.touch();return b''
                if len(chunks)>=3:port.write.assert_not_called()
                return chunks.pop(0)
            port.read.side_effect=read;port.write.side_effect=lambda data:len(data)
            modules={'serial':SimpleNamespace(Serial=lambda:port),'esptool.reset':SimpleNamespace(HardReset=MagicMock())}
            argv=['capture','--port','test','--output',str(root/'run'),'--stop-file',str(stop),'--reset',
                  '--replay-session',session,'--spec-id','G-0002.01','--spec-revision','2026-09-22','--workload','SD replay']
            with patch.object(sys,'argv',argv),patch.dict(sys.modules,modules):main()
            port.write.assert_called_once_with(('TRICORDER_REPLAY '+session+'\n').encode())
            manifest=json.loads((root/'run/manifest.json').read_text());self.assertTrue(manifest['replay'])
            summary=json.loads((root/'run/summary.json').read_text());self.assertEqual(summary['replay_state'],'complete')

    def test_explicit_spec_revision_and_workload_reach_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);stop=root/'stop';stop.touch();port=MagicMock()
            modules={'serial':SimpleNamespace(Serial=lambda:port),
                     'esptool.reset':SimpleNamespace(HardReset=MagicMock())}
            argv=['capture','--port','test','--output',str(root/'run'),'--stop-file',str(stop),
                  '--spec-id','G-0002.01','--spec-revision','2026-09-21',
                  '--workload','explicit-turn A/B; audio only']
            with patch.object(sys,'argv',argv),patch.dict(sys.modules,modules):main()
            manifest=json.loads((root/'run/manifest.json').read_text())
            self.assertEqual(manifest['spec_id'],'G-0002.01')
            self.assertEqual(manifest['spec_revision'],'2026-09-21')
            self.assertEqual(manifest['workload'],'explicit-turn A/B; audio only')

    def test_new_spec_requires_revision_and_workload_before_opening_port(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            argv=['capture','--port','test','--output',str(root/'run'),'--spec-id','G-0002.01']
            with patch.object(sys,'argv',argv),self.assertRaises(SystemExit):main()
            self.assertFalse((root/'run').exists())

    def test_guard_panic_is_failure_even_without_standard_abort_message(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);stop=root/'stop';port=MagicMock()
            def read(_):
                stop.touch()
                return b'JPEG DMA ownership unresolved: refusing error-path release\n'
            port.read.side_effect=read
            modules={'serial':SimpleNamespace(Serial=lambda:port),
                     'esptool.reset':SimpleNamespace(HardReset=MagicMock())}
            argv=['capture','--port','test','--output',str(root/'run'),'--stop-file',str(stop)]
            with patch.object(sys,'argv',argv),patch.dict(sys.modules,modules):
                with self.assertRaises(SystemExit): main()
            summary=json.loads((root/'run/summary.json').read_text())
            self.assertEqual(summary['status'],'fail')
            self.assertEqual(len(summary['capture_errors']),1)

    def test_stop_request_finalizes_missing_checks_as_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stop = root/'stop'
            stop.touch()
            port = MagicMock()
            modules = {'serial':SimpleNamespace(Serial=lambda:port),
                       'esptool.reset':SimpleNamespace(HardReset=MagicMock())}
            argv = ['capture', '--port', 'test-port', '--output', str(root/'run'),
                    '--seconds', '600', '--stop-file', str(stop), '--checks', 'camera_frame']
            with patch.object(sys, 'argv', argv), patch.dict(sys.modules, modules):
                main()
            port.read.assert_not_called()
            summary = json.loads((root/'run/summary.json').read_text())
            self.assertEqual(summary['status'], 'inconclusive')
            self.assertEqual(summary['checks']['camera_frame'], 'inconclusive')
