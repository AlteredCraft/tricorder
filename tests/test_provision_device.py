from pathlib import Path
import tempfile
import unittest

from tools.provision_device import load_config


class ProvisionTests(unittest.TestCase):
    def test_literal_values_aliases_and_redacted_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'env'
            p.write_text('WIFI_NAME="my wifi"\nWIFI_PASSWORD=abc!$`#def\n')
            self.assertEqual(load_config(p), {'ssid':'my wifi','password':'abc!$`#def'})
            p.write_text("WIFI_SSID=network\nWIFI_PASSWORD='eight chars'\n")
            self.assertEqual(load_config(p)['password'], 'eight chars')
            for value in ['WIFI_NAME=x\n', 'WIFI_NAME='+('x'*33)+'\nWIFI_PASSWORD=SECRET',
                          'WIFI_NAME=x\nWIFI_NAME=y\nWIFI_PASSWORD=SECRET']:
                p.write_text(value)
                with self.assertRaises(ValueError) as error:
                    load_config(p)
                self.assertNotIn('SECRET', str(error.exception))
