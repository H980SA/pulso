#!/usr/bin/env python3
"""Serve PULSO Mission Control and persist auditable, replayable sessions."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from hashlib import sha256
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from integrity import canonical, verify_chain


APP_ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 16 * 1024 * 1024
SESSION_RE = re.compile(r"^S-[0-9TZ-]{16,24}-[a-f0-9]{8}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SessionRepository:
    """Small SQLite boundary with a per-session tamper-evident event chain."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.db_path = state_dir / "mission-control.sqlite3"
        self.artifact_dir = state_dir / "artifacts"
        self._lock = threading.RLock()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  session_id TEXT PRIMARY KEY,
                  mission_id TEXT NOT NULL,
                  source TEXT NOT NULL,
                  mode TEXT NOT NULL CHECK(mode IN ('LIVE', 'REPLAY')),
                  started_at TEXT NOT NULL,
                  ended_at TEXT,
                  event_count INTEGER NOT NULL DEFAULT 0,
                  last_event_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS events (
                  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                  seq INTEGER NOT NULL,
                  topic TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  received_at_ms REAL NOT NULL,
                  captured_ns INTEGER,
                  payload_json TEXT NOT NULL,
                  artifact_sha256 TEXT,
                  previous_hash TEXT NOT NULL,
                  event_hash TEXT NOT NULL,
                  PRIMARY KEY(session_id, seq)
                );
                CREATE INDEX IF NOT EXISTS events_session_kind
                  ON events(session_id, kind, seq);
                """
            )

    def create_session(self, mission_id: str, source: str, mode: str = "LIVE") -> dict[str, Any]:
        if mode not in {"LIVE", "REPLAY"}:
            raise ValueError("mode must be LIVE or REPLAY")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        session_id = f"S-{stamp}-{uuid4().hex[:8]}"
        started_at = utc_now()
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO sessions(session_id, mission_id, source, mode, started_at) VALUES(?,?,?,?,?)",
                (session_id, mission_id.strip() or "M-001", source.strip() or "UNKNOWN", mode, started_at),
            )
        return self.read_session(session_id, include_events=False)

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (max(1, min(limit, 200)),)
            ).fetchall()
        return [self._session(row) for row in rows]

    def read_session(self, session_id: str, *, include_events: bool = True) -> dict[str, Any]:
        self._validate_session_id(session_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if row is None:
                raise KeyError(session_id)
            output = self._session(row)
            if include_events:
                events = db.execute(
                    "SELECT * FROM events WHERE session_id=? ORDER BY seq", (session_id,)
                ).fetchall()
                output["events"] = [self._event(event) for event in events]
                valid, detail = verify_chain(row, events, self.artifact_dir)
                output["integrity_valid"] = valid
                output["integrity_status"] = "VERIFIED" if valid else "INVALID"
                output["integrity_detail"] = detail
        return output

    def append_event(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        self._validate_session_id(session_id)
        event = value.get("event")
        if not isinstance(event, dict) or not isinstance(event.get("kind"), str):
            raise ValueError("event.kind is required")
        topic = value.get("topic") if isinstance(value.get("topic"), str) else "internal"
        received_at_ms = value.get("received_at_ms")
        if not isinstance(received_at_ms, (int, float)):
            raise ValueError("received_at_ms must be numeric")
        received_at_ms = float(received_at_ms)
        artifact_hash = self._store_artifact(value.get("artifact"))
        payload_json = canonical(event).decode()
        with self._lock, self.connect() as db:
            session = db.execute(
                "SELECT event_count,last_event_hash,ended_at FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if session is None:
                raise KeyError(session_id)
            if session["ended_at"]:
                raise ValueError("session is closed")
            seq = int(session["event_count"]) + 1
            previous_hash = session["last_event_hash"]
            digest_input = {
                "session_id": session_id,
                "seq": seq,
                "topic": topic,
                "received_at_ms": received_at_ms,
                "payload": event,
                "artifact_sha256": artifact_hash,
                "previous_hash": previous_hash,
            }
            event_hash = sha256(canonical(digest_input)).hexdigest()
            db.execute(
                """INSERT INTO events(
                     session_id,seq,topic,kind,received_at_ms,captured_ns,payload_json,
                     artifact_sha256,previous_hash,event_hash
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id, seq, topic, event["kind"], received_at_ms,
                    event.get("capturedNs") if isinstance(event.get("capturedNs"), int) else None,
                    payload_json, artifact_hash, previous_hash, event_hash,
                ),
            )
            db.execute(
                "UPDATE sessions SET event_count=?,last_event_hash=? WHERE session_id=?",
                (seq, event_hash, session_id),
            )
        return {"seq": seq, "event_hash": event_hash, "artifact_sha256": artifact_hash}

    def close_session(self, session_id: str) -> dict[str, Any]:
        self._validate_session_id(session_id)
        with self._lock, self.connect() as db:
            result = db.execute(
                "UPDATE sessions SET ended_at=COALESCE(ended_at,?) WHERE session_id=?",
                (utc_now(), session_id),
            )
            if result.rowcount == 0:
                raise KeyError(session_id)
        return self.read_session(session_id, include_events=False)

    def artifact(self, digest: str) -> tuple[bytes, str]:
        if not SHA_RE.fullmatch(digest):
            raise KeyError(digest)
        metadata = self.artifact_dir / f"{digest}.json"
        binary = self.artifact_dir / f"{digest}.bin"
        if not metadata.is_file() or not binary.is_file():
            raise KeyError(digest)
        info = json.loads(metadata.read_text())
        return binary.read_bytes(), str(info.get("content_type", "application/octet-stream"))

    def _store_artifact(self, artifact: Any) -> str | None:
        if artifact is None:
            return None
        if not isinstance(artifact, dict) or not isinstance(artifact.get("base64"), str):
            raise ValueError("artifact.base64 is required")
        try:
            body = base64.b64decode(artifact["base64"], validate=True)
        except ValueError as failure:
            raise ValueError("artifact.base64 is invalid") from failure
        if not body or len(body) > MAX_BODY_BYTES:
            raise ValueError("artifact size is invalid")
        digest = sha256(body).hexdigest()
        binary = self.artifact_dir / f"{digest}.bin"
        metadata = self.artifact_dir / f"{digest}.json"
        if not binary.exists():
            temporary = binary.with_suffix(f".tmp-{uuid4().hex}")
            temporary.write_bytes(body)
            os.replace(temporary, binary)
        if not metadata.exists():
            content_type = artifact.get("content_type")
            if content_type not in {"image/jpeg", "image/png", "application/octet-stream"}:
                content_type = "application/octet-stream"
            metadata.write_text(json.dumps({"sha256": digest, "bytes": len(body), "content_type": content_type}))
        return digest

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not SESSION_RE.fullmatch(session_id):
            raise KeyError(session_id)

    @staticmethod
    def _session(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"], "mission_id": row["mission_id"],
            "source": row["source"], "mode": row["mode"], "started_at": row["started_at"],
            "ended_at": row["ended_at"], "event_count": row["event_count"],
            "integrity_hash": row["last_event_hash"] or None,
        }

    @staticmethod
    def _event(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "seq": row["seq"], "topic": row["topic"], "kind": row["kind"],
            "received_at_ms": row["received_at_ms"], "captured_ns": row["captured_ns"],
            "event": json.loads(row["payload_json"]), "artifact_sha256": row["artifact_sha256"],
            "previous_hash": row["previous_hash"] or None, "event_hash": row["event_hash"],
        }


class MissionControlHandler(SimpleHTTPRequestHandler):
    repository: SessionRepository
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json({"status": "ok", "persistence": "sqlite"})
            return
        if path == "/api/sessions":
            query = parse_qs(urlsplit(self.path).query)
            self._json({"sessions": self.repository.list_sessions(int(query.get("limit", [50])[0]))})
            return
        match = re.fullmatch(r"/api/sessions/([^/]+)(/export)?", path)
        if match:
            try:
                value = self.repository.read_session(match.group(1))
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "session not found")
                return
            if match.group(2):
                self._json(value, download=f"{match.group(1)}.json")
            else:
                self._json(value)
            return
        match = re.fullmatch(r"/api/artifacts/([a-f0-9]{64})", path)
        if match:
            try:
                body, content_type = self.repository.artifact(match.group(1))
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "artifact not found")
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        try:
            body = self._read_json()
            if path == "/api/sessions":
                value = self.repository.create_session(
                    str(body.get("mission_id", "M-001")), str(body.get("source", "UNKNOWN")),
                    str(body.get("mode", "LIVE")),
                )
                self._json(value, status=HTTPStatus.CREATED)
                return
            match = re.fullmatch(r"/api/sessions/([^/]+)/events", path)
            if match:
                self._json(self.repository.append_event(match.group(1), body), status=HTTPStatus.CREATED)
                return
            match = re.fullmatch(r"/api/sessions/([^/]+)/close", path)
            if match:
                self._json(self.repository.close_session(match.group(1)))
                return
            self._error(HTTPStatus.NOT_FOUND, "API route not found")
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "session not found")
        except (ValueError, json.JSONDecodeError) as failure:
            self._error(HTTPStatus.BAD_REQUEST, str(failure))

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body size is invalid")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _json(self, value: Any, *, status: HTTPStatus = HTTPStatus.OK, download: str | None = None) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status=status)

    def translate_path(self, request_path: str) -> str:
        path = unquote(urlsplit(request_path).path)
        relative = path.lstrip("/") or "index.html"
        candidate = (APP_ROOT / relative).resolve()
        try:
            candidate.relative_to(APP_ROOT)
        except ValueError:
            return str(APP_ROOT / "__not_found__")
        return str(candidate)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; script-src 'self'; "
            "style-src 'self'; connect-src 'self' ws: wss:; base-uri 'none'; frame-ancestors 'none'",
        )
        super().end_headers()

    def list_directory(self, path: str):
        self.send_error(HTTPStatus.NOT_FOUND, "Directory listing disabled")
        return None


def default_state_dir() -> Path:
    configured = os.getenv("PULSO_MISSION_STATE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    base = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local/state"))
    return base / "pulso/mission-control"


def build_server(bind: str, port: int, state_dir: Path) -> ThreadingHTTPServer:
    repository = SessionRepository(state_dir)
    handler = type("ConfiguredMissionControlHandler", (MissionControlHandler,), {"repository": repository})
    return ThreadingHTTPServer((bind, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve PULSO mission control")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    args = parser.parse_args()
    server = build_server(args.bind, args.port, args.state_dir)
    print(f"PULSO mission control: http://{args.bind}:{args.port}/", flush=True)
    print(f"PULSO session store: {args.state_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
