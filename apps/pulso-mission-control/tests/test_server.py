from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import SessionRepository, build_server  # noqa: E402


class SessionRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = SessionRepository(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_appends_hash_chained_events_and_round_trips_artifact(self):
        session = self.repository.create_session("M-001", "GAZEBO_HIL")
        first = self.repository.append_event(
            session["session_id"],
            {
                "topic": "/pulso/hil/observation",
                "received_at_ms": 10.5,
                "event": {"kind": "observation", "capturedNs": 10, "source": "GAZEBO_HIL"},
            },
        )
        jpeg = b"\xff\xd8real-frame\xff\xd9"
        second = self.repository.append_event(
            session["session_id"],
            {
                "topic": "/pulso/phone/rgb/compressed",
                "received_at_ms": 11,
                "event": {"kind": "camera-image", "capturedNs": 11},
                "artifact": {
                    "content_type": "image/jpeg",
                    "base64": base64.b64encode(jpeg).decode(),
                },
            },
        )

        stored = self.repository.read_session(session["session_id"])
        self.assertEqual(stored["event_count"], 2)
        self.assertEqual(stored["events"][1]["previous_hash"], first["event_hash"])
        self.assertEqual(stored["integrity_hash"], second["event_hash"])
        body, content_type = self.repository.artifact(second["artifact_sha256"])
        self.assertEqual(body, jpeg)
        self.assertEqual(content_type, "image/jpeg")
        self.assertTrue(stored["integrity_valid"])
        self.assertEqual(stored["integrity_status"], "VERIFIED")

    def test_tampered_event_is_rejected_by_integrity_verifier(self):
        session = self.repository.create_session("M-001", "GAZEBO_HIL")
        self.repository.append_event(
            session["session_id"],
            {
                "topic": "/pulso/hil/observation",
                "received_at_ms": 10,
                "event": {"kind": "observation", "source": "GAZEBO_HIL"},
            },
        )
        with self.repository.connect() as db:
            db.execute(
                "UPDATE events SET payload_json=? WHERE session_id=? AND seq=1",
                ('{"kind":"observation","source":"FORGED"}', session["session_id"]),
            )

        stored = self.repository.read_session(session["session_id"])

        self.assertFalse(stored["integrity_valid"])
        self.assertEqual(stored["integrity_status"], "INVALID")
        self.assertIn("event hash mismatch", stored["integrity_detail"])

    def test_tampered_artifact_is_rejected_by_integrity_verifier(self):
        session = self.repository.create_session("M-001", "ANDROID_REAL")
        receipt = self.repository.append_event(
            session["session_id"],
            {
                "topic": "/pulso/phone/rgb/compressed",
                "received_at_ms": 11,
                "event": {"kind": "camera-image", "capturedNs": 11},
                "artifact": {
                    "content_type": "image/jpeg",
                    "base64": base64.b64encode(b"measured").decode(),
                },
            },
        )
        (self.repository.artifact_dir / f'{receipt["artifact_sha256"]}.bin').write_bytes(b"forged")

        stored = self.repository.read_session(session["session_id"])

        self.assertFalse(stored["integrity_valid"])
        self.assertIn("artifact hash mismatch", stored["integrity_detail"])

    def test_closed_session_rejects_new_events(self):
        session = self.repository.create_session("M-001", "ANDROID_REAL")
        self.repository.close_session(session["session_id"])
        with self.assertRaisesRegex(ValueError, "closed"):
            self.repository.append_event(
                session["session_id"],
                {"topic": "internal", "received_at_ms": 1, "event": {"kind": "observation"}},
            )

    def test_export_shape_is_json_serializable_and_lists_sessions(self):
        session = self.repository.create_session("M-009", "GAZEBO_HIL")
        exported = self.repository.read_session(session["session_id"])
        self.assertEqual(exported["events"], [])
        self.assertEqual(self.repository.list_sessions()[0]["mission_id"], "M-009")
        json.dumps(exported)


class SessionHttpApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.server = build_server("127.0.0.1", 0, Path(self.temporary.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(self, path, *, method="GET", body=None):
        encoded = json.dumps(body).encode() if body is not None else None
        request = Request(
            self.base + path,
            data=encoded,
            method=method,
            headers={"Content-Type": "application/json"} if encoded else {},
        )
        with urlopen(request, timeout=2) as response:
            return response.status, response.headers, json.loads(response.read())

    def test_create_append_list_read_close_and_export(self):
        status, _, session = self.request(
            "/api/sessions", method="POST", body={"mission_id": "M-001", "source": "GAZEBO_HIL"}
        )
        self.assertEqual(status, 201)
        session_id = session["session_id"]
        status, _, receipt = self.request(
            f"/api/sessions/{session_id}/events",
            method="POST",
            body={
                "topic": "/pulso/hil/observation",
                "received_at_ms": 3,
                "event": {"kind": "observation", "source": "GAZEBO_HIL"},
            },
        )
        self.assertEqual((status, receipt["seq"]), (201, 1))
        _, _, listing = self.request("/api/sessions")
        self.assertEqual(listing["sessions"][0]["session_id"], session_id)
        _, _, detail = self.request(f"/api/sessions/{session_id}")
        self.assertEqual(detail["events"][0]["topic"], "/pulso/hil/observation")
        self.assertTrue(detail["integrity_valid"])
        status, headers, exported = self.request(f"/api/sessions/{session_id}/export")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(exported["integrity_hash"], receipt["event_hash"])
        _, _, closed = self.request(f"/api/sessions/{session_id}/close", method="POST", body={})
        self.assertIsNotNone(closed["ended_at"])


if __name__ == "__main__":
    unittest.main()
