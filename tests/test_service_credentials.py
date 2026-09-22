from pathlib import Path
import tempfile
import unittest
from tools.service_credentials import load_api_key


class ServiceCredentialTests(unittest.TestCase):
    def test_provider_specific_key_and_literal_file_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'local.env'
            path.write_text('# local only\nOPENAI_API_KEY=direct-test\nOPENROUTER_API_KEY="router-test"\n')
            self.assertEqual(load_api_key('openrouter',path),'router-test')
            self.assertEqual(load_api_key('openai',path),'direct-test')
            path.write_text('OPENAI_API_KEY=direct-test\n')
            with self.assertRaises(ValueError):load_api_key('openrouter',path)

    def test_duplicate_empty_and_malformed_keys_fail_without_disclosing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'local.env'
            for contents in ('OPENROUTER_API_KEY=secret-one\nOPENROUTER_API_KEY=secret-two',
                             'OPENROUTER_API_KEY=', 'OPENROUTER_API_KEY="secret with space"'):
                path.write_text(contents)
                with self.assertRaises(ValueError) as caught:load_api_key('openrouter',path)
                self.assertNotIn('secret',str(caught.exception))

    def test_environment_and_route_validation(self):
        self.assertEqual(load_api_key('openrouter',environ={'OPENROUTER_API_KEY':'router-test'}),'router-test')
        with self.assertRaises(ValueError):load_api_key('openrouter',environ={'OPENAI_API_KEY':'wrong-key'})
        with self.assertRaises(ValueError):load_api_key('unknown',environ={})
