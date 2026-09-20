"""Verify two full flash reads before overwriting the connected board."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def inspect_backup(first: Path, second: Path, expected_size: int) -> dict:
    if expected_size <= 0:
        raise ValueError("expected size must be positive")
    digests = []
    for path in (first, second):
        if path.stat().st_size != expected_size:
            raise ValueError(f"backup size mismatch: {path}")
        content = path.read_bytes()
        if content == b"\xff" * expected_size or content == b"\x00" * expected_size:
            raise ValueError(f"blank backup: {path}")
        digests.append(hashlib.sha256(content).hexdigest())
    if first.samefile(second):
        raise ValueError("two independent read files are required")
    if digests[0] != digests[1]:
        raise ValueError("flash reads differ; preserve both and investigate")
    return {"status": "verified", "size_bytes": expected_size, "sha256": digests[0],
            "reads": [str(first.resolve()), str(second.resolve())],
            "limit": "Matching full reads; successful boot after restoration is not yet tested."}


def write_manifest(path: Path, backup: dict, chip: str, serial: str) -> None:
    record = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "chip": chip, "serial": serial, "backup": backup}
    with path.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--size", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--chip", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = inspect_backup(args.first, args.second, args.size)
    write_manifest(args.output, result, args.chip, args.serial)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
