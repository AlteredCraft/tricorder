"""Reassemble bounded device captures, publishing only complete checked bytes."""
import base64
import binascii
import hashlib
import json
import os
import re
from pathlib import Path


class CaptureStore:
    MAX_BYTES = 16 * 1024 * 1024
    MAX_ACTIVE = 4

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.active = {}
        self.seen = set()

    def _metadata(self, capture_id, record):
        path = self.directory / f"{capture_id}.json"
        temporary = self.directory / f"{capture_id}.json.tmp"
        with temporary.open("x") as stream:
            json.dump(record, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def consume(self, event):
        kind = event["event"]
        if kind not in ("capture_start", "capture_chunk", "capture_end"):
            return
        capture_id = event.get("capture_id")
        if not isinstance(capture_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", capture_id):
            raise ValueError("invalid capture ID")
        partial = self.directory / f"{capture_id}.partial"
        if kind == "capture_start":
            if capture_id in self.active:
                self.active[capture_id]["invalid"].append("duplicate capture start")
                raise ValueError("capture ID already exists")
            if capture_id in self.seen or any((self.directory/f"{capture_id}{suffix}").exists()
                                            for suffix in (".bin", ".partial", ".json")):
                raise ValueError("capture ID already exists")
            size = event.get("size_bytes")
            if type(size) is not int or not 0 < size <= self.MAX_BYTES:
                raise ValueError("capture size outside bounds")
            if len(self.active) >= self.MAX_ACTIVE or len(self.seen) >= 1024:
                raise ValueError("capture count outside bounds")
            if not isinstance(event.get("boot_id"), str) or not event["boot_id"]:
                raise ValueError("missing capture boot")
            with partial.open("xb"):
                pass
            state = {"metadata": dict(event), "received": 0, "hash": hashlib.sha256(), "invalid": []}
            self.active[capture_id] = state
            self.seen.add(capture_id)
            self._metadata(capture_id, {**event, "status": "incomplete", "received_bytes": 0})
            return
        if capture_id not in self.active:
            raise ValueError("capture has no active start")
        state = self.active[capture_id]
        metadata = state["metadata"]
        try:
            if event.get("boot_id") != metadata["boot_id"]:
                raise ValueError("capture boot mismatch")
            if kind == "capture_chunk":
                if type(event.get("offset")) is not int or event["offset"] != state["received"]:
                    raise ValueError("capture offset gap or duplicate")
                try:
                    data = base64.b64decode(event["data"], validate=True)
                except (KeyError, ValueError, TypeError, binascii.Error) as error:
                    raise ValueError("invalid capture base64") from error
                if not data or len(data) > 4096 or state["received"] + len(data) > metadata["size_bytes"]:
                    raise ValueError("capture chunk size outside bounds")
                with partial.open("ab") as stream:
                    stream.write(data)
                state["hash"].update(data)
                state["received"] += len(data)
            else:
                if state["received"] != metadata["size_bytes"]:
                    raise ValueError("capture final size mismatch")
                digest = state["hash"].hexdigest()
                if digest != event.get("sha256"):
                    raise ValueError("capture digest mismatch")
                if state["invalid"]:
                    raise ValueError("capture has earlier rejected events")
                with partial.open("rb") as stream:
                    os.fsync(stream.fileno())
                # New private run directory and exclusive start protect this path.
                partial.rename(self.directory/f"{capture_id}.bin")
                self._metadata(capture_id, {**metadata, "status": "complete",
                                           "received_bytes": state["received"], "sha256": digest})
                del self.active[capture_id]
        except ValueError as error:
            state["invalid"].append(str(error))
            raise

    def close(self):
        incomplete = list(self.active)
        for capture_id, state in self.active.items():
            self._metadata(capture_id, {**state["metadata"], "status": "incomplete",
                                       "received_bytes": state["received"], "errors": state["invalid"]})
        self.active.clear()
        return incomplete
