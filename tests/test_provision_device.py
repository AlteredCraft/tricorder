from pathlib import Path
import tempfile
import unittest

from tools.provision_device import load_config, with_known


class ProvisionTests(unittest.TestCase):
    def test_known_networks(self):
        with tempfile.TemporaryDirectory() as d:
            home, ap = Path(d)/'home', Path(d)/'ap'
            home.write_text('WIFI_NAME=home\nWIFI_PASSWORD=SECRETSECRET\n')
            ap.write_text('WIFI_NAME=Tricorder\nWIFI_PASSWORD=eight-chars\nWIFI_MODE=ap\n')
            base = load_config(ap)
            self.assertEqual(with_known(base, []), base)
            self.assertEqual(with_known(base, [home])['known'], [{'ssid':'home','password':'SECRETSECRET'}])
            for paths in ([ap], [home]*5):
                with self.assertRaises(ValueError) as error:
                    with_known(base, paths)
                self.assertNotIn('SECRET', str(error.exception))
            home.write_text('WIFI_NAME='+'n'*32+'\nWIFI_PASSWORD='+'p'*63+'\n')
            with_known(base, [home]*4)

    def test_literal_values_aliases_and_redacted_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'env'
            p.write_text('WIFI_NAME="my wifi"\nWIFI_PASSWORD=abc!$`#def\n')
            self.assertEqual(load_config(p), {'ssid':'my wifi','password':'abc!$`#def'})
            p.write_text("WIFI_SSID=network\nWIFI_PASSWORD='eight chars'\n")
            self.assertEqual(load_config(p)['password'], 'eight chars')
            p.write_text('WIFI_NAME=Tricorder\nWIFI_PASSWORD=eight-chars\nWIFI_MODE=ap\n')
            self.assertEqual(load_config(p), {'ssid':'Tricorder','password':'eight-chars','mode':'ap'})
            p.write_text('WIFI_NAME=Tricorder\nWIFI_PASSWORD=eight-chars\nWIFI_MODE=station\n')
            self.assertEqual(load_config(p), {'ssid':'Tricorder','password':'eight-chars'})
            for value in ['WIFI_NAME=x\nWIFI_PASSWORD=SECRET\nWIFI_MODE=ap\n', 'WIFI_NAME=x\nWIFI_PASSWORD=SECRETSECRET\nWIFI_MODE=mesh\n',
                          'WIFI_NAME=x\n', 'WIFI_NAME='+('x'*33)+'\nWIFI_PASSWORD=SECRET',
                          'WIFI_NAME=x\nWIFI_NAME=y\nWIFI_PASSWORD=SECRET']:
                p.write_text(value)
                with self.assertRaises(ValueError) as error:
                    load_config(p)
                self.assertNotIn('SECRET', str(error.exception))
