import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from tools.capture_serial import main


class CaptureSerialTests(unittest.TestCase):
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
