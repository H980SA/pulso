"""Tamper-evident session verification shared by read and replay boundaries."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def verify_chain(
    session: sqlite3.Row,
    events: list[sqlite3.Row],
    artifact_dir: Path,
) -> tuple[bool, str]:
    """Recompute the complete event chain and every referenced binary hash."""
    previous_hash = ""
    for expected_seq, row in enumerate(events, start=1):
        if int(row["seq"]) != expected_seq:
            return False, f"event sequence breaks at {expected_seq}"
        if row["previous_hash"] != previous_hash:
            return False, f"previous hash mismatch at event {expected_seq}"
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return False, f"invalid payload JSON at event {expected_seq}"
        artifact_hash = row["artifact_sha256"]
        if artifact_hash:
            binary = artifact_dir / f"{artifact_hash}.bin"
            metadata = artifact_dir / f"{artifact_hash}.json"
            if not binary.is_file() or not metadata.is_file():
                return False, f"artifact missing at event {expected_seq}"
            if sha256(binary.read_bytes()).hexdigest() != artifact_hash:
                return False, f"artifact hash mismatch at event {expected_seq}"
        digest_input = {
            "session_id": session["session_id"],
            "seq": expected_seq,
            "topic": row["topic"],
            "received_at_ms": float(row["received_at_ms"]),
            "payload": payload,
            "artifact_sha256": artifact_hash,
            "previous_hash": previous_hash,
        }
        expected_hash = sha256(canonical(digest_input)).hexdigest()
        if row["event_hash"] != expected_hash:
            return False, f"event hash mismatch at event {expected_seq}"
        previous_hash = expected_hash
    if int(session["event_count"]) != len(events):
        return False, "session event count mismatch"
    if session["last_event_hash"] != previous_hash:
        return False, "session head hash mismatch"
    return True, f"{len(events)} event(s) and referenced artifacts verified"
