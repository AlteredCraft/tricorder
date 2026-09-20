import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.captures import CaptureStore


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.store = CaptureStore(self.root)

    def start(self, capture_id="frame-1", size=6, boot="boot-a"):
        self.store.consume({"event": "capture_start", "capture_id": capture_id,
                            "boot_id": boot, "size_bytes": size, "format": "rgb565le",
                            "width": 3, "height": 1})

    def chunk(self, payload, offset=0, boot="boot-a"):
        self.store.consume({"event": "capture_chunk", "capture_id": "frame-1", "boot_id": boot,
                            "offset": offset, "data": base64.b64encode(payload).decode()})

    def finish(self, payload=b"abcdef"):
        self.store.consume({"event": "capture_end", "capture_id": "frame-1", "boot_id": "boot-a",
                            "sha256": hashlib.sha256(payload).hexdigest()})

    def test_complete_capture_requires_size_and_digest(self):
        self.start()
        self.chunk(b"abc")
        self.chunk(b"def", 3)
        self.finish()
        self.assertEqual((self.root/"frame-1.bin").read_bytes(), b"abcdef")
        record = json.loads((self.root/"frame-1.json").read_text())
        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["width"], 3)

    def test_wrong_digest_keeps_capture_incomplete(self):
        self.start()
        self.chunk(b"abcdef")
        with self.assertRaisesRegex(ValueError, "digest"):
            self.finish(b"ABCDEF")
        self.assertFalse((self.root/"frame-1.bin").exists())

    def test_truncated_capture_cannot_be_finalized(self):
        self.start()
        self.chunk(b"abc")
        with self.assertRaisesRegex(ValueError, "size"):
            self.finish(b"abc")

    def test_gap_and_duplicate_are_rejected(self):
        self.start()
        self.chunk(b"abc")
        for offset in (0, 4):
            with self.assertRaisesRegex(ValueError, "offset"):
                self.chunk(b"def", offset)

    def test_session_mismatch_is_rejected(self):
        self.start()
        with self.assertRaisesRegex(ValueError, "boot"):
            self.chunk(b"abcdef", boot="old-boot")

    def test_id_cannot_escape_capture_directory(self):
        with self.assertRaises(ValueError):
            self.start("../escape")

    def test_existing_evidence_is_never_replaced(self):
        self.start()
        self.chunk(b"abcdef")
        self.finish()
        with self.assertRaises(ValueError):
            self.start()
        self.assertEqual((self.root/"frame-1.bin").read_bytes(), b"abcdef")

    def test_unfinished_capture_is_marked_incomplete(self):
        self.start()
        self.chunk(b"abc")
        incomplete = self.store.close()
        self.assertEqual(incomplete, ["frame-1"])
        self.assertEqual(json.loads((self.root/"frame-1.json").read_text())["status"], "incomplete")
        self.assertEqual((self.root/"frame-1.partial").read_bytes(), b"abc")

    def test_capture_allocation_is_bounded(self):
        with self.assertRaises(ValueError):
            self.start(size=100_000_000)

    def test_extra_bytes_are_rejected(self):
        self.start()
        with self.assertRaises(ValueError):
            self.chunk(b"abcdefgh")

    def test_duplicate_start_cannot_later_publish_ambiguous_capture(self):
        self.start()
        with self.assertRaises(ValueError):
            self.start(size=3)
        self.chunk(b"abcdef")
        with self.assertRaisesRegex(ValueError, "earlier rejected"):
            self.finish()
        self.assertFalse((self.root/"frame-1.bin").exists())


if __name__ == "__main__":
    unittest.main()
