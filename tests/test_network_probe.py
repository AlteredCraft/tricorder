import unittest

from tools.network_probe import validate_echo


class NetworkProbeTests(unittest.TestCase):
    def test_requires_exact_nonce_boot_and_device_timestamp(self):
        response = {'nonce': 'a'*32, 'boot_id': 'b'*32, 'device_us': 123}
        validate_echo(response, 'a'*32, 'b'*32)
        for field, value in [('nonce', 'c'*32), ('boot_id', 'c'*32),
                             ('device_us', -1), ('device_us', True)]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    validate_echo({**response, field: value}, 'a'*32, 'b'*32)

    def test_missing_fields_are_not_success(self):
        with self.assertRaises(ValueError):
            validate_echo({}, 'a'*32, 'b'*32)
