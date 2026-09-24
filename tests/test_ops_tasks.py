"""Operations task catalogue: discovery, validation and command building (no TUI)."""
from datetime import datetime
from pathlib import Path
import json
import tempfile
import unittest

from tools import ops_tasks as ops

TAB5 = 'E8:F6:0A:E2:E0:0E'


class WifiDiscoveryTests(unittest.TestCase):
    def test_lists_wifi_env_files_with_network_name_never_password(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'.env.local.home').write_text('WIFI_NAME="Home Net"\nWIFI_PASSWORD=s3cret\n')
            (root/'.env.local.hotspot').write_text("WIFI_SSID=Sam’s iPhone\nWIFI_PASSWORD=pw\n")
            (root/'.env.local.openrouter').write_text('OPENROUTER_API_KEY=sk-x\n')  # not Wi-Fi
            (root/'.env.local.broken').write_text('WIFI_NAME=x\nWIFI_NAME=y\nWIFI_PASSWORD=p\n')
            (root/'.env').write_text('WIFI_NAME=ignored\nWIFI_PASSWORD=p\n')
            found = ops.wifi_env_files(root)
            self.assertEqual([(f.path.name, f.ssid, f.error) for f in found], [
                ('.env.local.broken', None, 'Duplicate environment key'),
                ('.env.local.home', 'Home Net', None),
                ('.env.local.hotspot', 'Sam’s iPhone', None)])
            self.assertNotIn('s3cret', repr(found))

    def test_tab5_port_matches_verified_usb_serial_only(self):
        ports = [('/dev/cu.Bluetooth', None), ('/dev/cu.usbmodem1', 'OTHER'), ('/dev/cu.usbmodem2101', TAB5)]
        self.assertEqual(ops.tab5_port(ports), '/dev/cu.usbmodem2101')
        self.assertIsNone(ops.tab5_port(ports[:2]))

    def test_mac_ipv4_uses_first_interface_with_an_address(self):
        answers = {'en0': '', 'en1': '192.168.1.20\n'}
        self.assertEqual(ops.mac_ipv4(lambda iface: answers.get(iface, '')), '192.168.1.20')
        self.assertIsNone(ops.mac_ipv4(lambda iface: ''))


class ProvisionCommandTests(unittest.TestCase):
    def setUp(self):
        self.root = Path('/repo')
        self.when = datetime(2026, 9, 24, 14, 5, 9)

    def plan(self, **changes):
        values = dict(env_file=self.root/'.env.local.home', port='/dev/cu.usbmodem2101',
                      mac_ip='192.168.1.20', service_port=8765)
        values.update(changes)
        return ops.provision_plan(self.root, when=self.when, **values)

    def test_builds_the_existing_provisioning_command(self):
        plan = self.plan()
        self.assertEqual(plan.errors, [])
        self.assertEqual(plan.endpoint, 'ws://192.168.1.20:8765/')
        self.assertEqual(plan.output, self.root/'.local/runs/20260924-140509-provision')
        self.assertEqual(plan.argv, [
            str(self.root/'.tools/python-env/bin/python'), '-m', 'tools.provision_device',
            '--env', str(self.root/'.env.local.home'), '--port', '/dev/cu.usbmodem2101',
            '--endpoint', 'ws://192.168.1.20:8765/',
            '--output', str(self.root/'.local/runs/20260924-140509-provision')])

    def test_missing_inputs_are_errors_not_guesses(self):
        plan = self.plan(port=None, mac_ip=None, env_file=None)
        self.assertEqual(plan.argv, [])
        self.assertEqual(plan.errors, ['Choose a Wi-Fi env file', 'Tab5 not found on USB',
                                       'Mac has no LAN IPv4 address'])

    def test_non_private_mac_address_is_rejected(self):
        self.assertIn('Mac address 8.8.8.8 is not a private LAN address', self.plan(mac_ip='8.8.8.8').errors)


class ProvisionResultTests(unittest.TestCase):
    def lines(self, *events):
        return [json.dumps(e) for e in events]+['not json']

    def test_reports_tab5_address_subnet_and_reachability(self):
        out = self.lines({'event': 'storage_config', 'result': 'pass', 'source': 'usb'},
                         {'event': 'wifi_address', 'ipv4': '192.168.1.44'})
        r = ops.provision_result(out, mac_ip='192.168.1.20', reachable=lambda ip: True)
        self.assertEqual((r.tab5_ip, r.same_subnet, r.reachable, r.problems), ('192.168.1.44', True, True, []))

    def test_client_isolation_and_other_subnet_are_explained(self):
        out = self.lines({'event': 'storage_config', 'result': 'pass', 'source': 'usb'},
                         {'event': 'wifi_address', 'ipv4': '172.16.101.186'})
        r = ops.provision_result(out, mac_ip='172.16.101.234', reachable=lambda ip: False)
        self.assertEqual(r.problems, ['Mac cannot reach the Tab5 at 172.16.101.186 '
                                      '(the network may block device-to-device traffic; try a hotspot)'])
        r = ops.provision_result(out, mac_ip='10.0.0.5', reachable=lambda ip: True)
        self.assertIn('Tab5 (172.16.101.186) and Mac (10.0.0.5) are on different subnets; '
                      'join the Mac to the same network', r.problems)

    def test_no_address_after_provisioning_is_a_problem(self):
        out = self.lines({'event': 'storage_config', 'result': 'pass', 'source': 'usb'})
        r = ops.provision_result(out, mac_ip='192.168.1.20', reachable=lambda ip: True)
        self.assertIsNone(r.tab5_ip)
        self.assertEqual(r.problems, ['Tab5 saved the settings but did not report a Wi-Fi address; '
                                      'check the network name, password and 2.4 GHz'])


class CatalogueTests(unittest.TestCase):
    def test_wifi_provision_is_registered(self):
        self.assertIn('wifi', {task.key for task in ops.TASKS})


if __name__ == '__main__':
    unittest.main()
