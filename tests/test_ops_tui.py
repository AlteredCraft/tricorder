"""Pilot test of the ops TUI with faked hardware. Needs Textual:
`uv run --with 'textual>=8.2,<9' python -m unittest discover -s tests -p test_ops_tui.py`"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from tools import ops_tasks as ops

HAS_TEXTUAL = importlib.util.find_spec('textual') is not None


@unittest.skipUnless(HAS_TEXTUAL, 'Textual not installed in this environment')
class OpsTuiTests(unittest.IsolatedAsyncioTestCase):
    async def run_app(self, tab5_ip, reachable):
        from tools.ops import OpsApp
        from textual.widgets import Button, Select, Static
        events = [{'event': 'storage_config', 'result': 'pass', 'source': 'usb'},
                  {'event': 'wifi_address', 'ipv4': tab5_ip}]
        fake = ';'.join(f'print({json.dumps(json.dumps(e))})' for e in events)
        def plan(root, **kwargs):
            p = ops.provision_plan(root, **kwargs)
            if not p.errors:
                p.argv = [sys.executable, '-c', fake]  # Stands in for provision_device.
            return p
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'.env.local.home').write_text('WIFI_NAME=Home Net\nWIFI_PASSWORD=secret\n')
            (root/'.env.local.openrouter').write_text('OPENROUTER_API_KEY=x\n')
            app = OpsApp(root, ports=lambda: [('/dev/cu.usbmodem9', ops.TAB5_USB_SERIAL)],
                         ip_lookup=lambda: '192.168.1.20', reachable=lambda ip: reachable, plan=plan)
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                self.assertEqual(app.query_one('#env', Select).value, str(root/'.env.local.home'))
                plan_text = str(app.query_one('#plan', Static).render())
                self.assertIn('Home Net', plan_text)
                self.assertIn('ws://192.168.1.20:8765/', plan_text)
                self.assertNotIn('secret', plan_text)
                self.assertFalse(app.query_one('#run', Button).disabled)
                await pilot.press('r')
                await app.workers.wait_for_complete()
                await pilot.pause()
                return str(app.query_one('#result', Static).render())

    async def test_successful_provision_reports_reachable_address(self):
        text = await self.run_app('192.168.1.44', True)
        self.assertIn('Tab5 is at 192.168.1.44, reachable', text)

    async def test_isolated_network_is_explained(self):
        text = await self.run_app('192.168.1.44', False)
        self.assertIn('cannot reach the Tab5', text)

    async def test_missing_tab5_disables_run(self):
        from tools.ops import OpsApp
        from textual.widgets import Button, Static
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'.env.local.home').write_text('WIFI_NAME=Home\nWIFI_PASSWORD=p\n')
            app = OpsApp(Path(d), ports=lambda: [], ip_lookup=lambda: '192.168.1.20')
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                self.assertTrue(app.query_one('#run', Button).disabled)
                self.assertIn('Tab5 not found on USB', str(app.query_one('#plan', Static).render()))


if __name__ == '__main__':
    unittest.main()
