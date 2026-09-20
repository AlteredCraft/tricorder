import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.recovery import inspect_backup, write_manifest


class RecoveryTests(unittest.TestCase):
    def test_two_equal_complete_reads_establish_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = bytes(range(256)) * 16
            for name in ("first.bin", "second.bin"):
                (root / name).write_bytes(payload)
            result = inspect_backup(root / "first.bin", root / "second.bin", 4096)
            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest())
            write_manifest(root / "recovery.json", result, "esp32p4", "unit-test")
            self.assertEqual(json.loads((root / "recovery.json").read_text())["backup"], result)

    def test_matching_truncated_reads_do_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short.bin"
            path.write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "size"):
                inspect_backup(path, path, 4096)

    def test_different_reads_do_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.bin", Path(directory) / "b.bin"
            a.write_bytes(b"a" * 4096)
            b.write_bytes(b"b" * 4096)
            with self.assertRaisesRegex(ValueError, "differ"):
                inspect_backup(a, b, 4096)

    def test_blank_flash_is_not_a_recovery_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blank.bin"
            path.write_bytes(b"\xff" * 4096)
            with self.assertRaisesRegex(ValueError, "blank"):
                inspect_backup(path, path, 4096)

    def test_missing_read_is_not_a_pass(self):
        with self.assertRaises(FileNotFoundError):
            inspect_backup(Path("missing-first.bin"), Path("missing-second.bin"), 4096)

    def test_same_file_cannot_count_as_two_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "read.bin"
            path.write_bytes(bytes(range(256)) * 16)
            with self.assertRaisesRegex(ValueError, "independent"):
                inspect_backup(path, path, 4096)

    def test_alias_cannot_count_as_second_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path, alias = Path(directory) / "read.bin", Path(directory) / "alias.bin"
            path.write_bytes(bytes(range(256)) * 16)
            alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError, "independent"):
                inspect_backup(path, alias, 4096)

    def test_manifest_does_not_overwrite_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recovery.json"
            path.write_text("original")
            with self.assertRaises(FileExistsError):
                write_manifest(path, {}, "esp32p4", "unit-test")
            self.assertEqual(path.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
