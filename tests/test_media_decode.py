import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from tools.inspect_capture import load_verified, split_pcm


class MediaDecodeTests(unittest.TestCase):
    def test_slots_keep_signed_samples_and_order(self):
        data = struct.pack('<8h', -32768, -1, 0, 32767, 3, 4, 5, 6)
        channels = split_pcm(data, 4)
        self.assertEqual(channels, [(-32768, 3), (-1, 4), (0, 5), (32767, 6)])

    def test_partial_interleaved_frame_is_rejected(self):
        with self.assertRaises(ValueError):
            split_pcm(b'\x00'*6, 4)

    def test_modified_complete_capture_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'capture.json'
            path.write_text(json.dumps({'status':'complete', 'size_bytes':3,
                                        'sha256':hashlib.sha256(b'abc').hexdigest()}))
            path.with_suffix('.bin').write_bytes(b'xyz')
            with self.assertRaises(ValueError):
                load_verified(path)

    def test_incomplete_capture_is_never_previewed_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'capture.json'
            path.write_text(json.dumps({'status':'incomplete'}))
            with self.assertRaises(ValueError):
                load_verified(path)
