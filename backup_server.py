#!/usr/bin/env python3
"""Tiny backup server for Yours.

Endpoints:
- GET  /health
- GET  /api/yours-sync/status
- GET  /api/yours-backups/latest
- POST /api/yours-backups/latest
- POST /api/yours-sync/events

Optional auth:
- Set YOURS_BACKUP_TOKEN, then send Authorization: Bearer <token>.
"""

from __future__ import annotations

import os
import json
import re
import threading
import tempfile
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BACKUP_PATH = "/api/yours-backups/latest"
EVENTS_PATH = "/api/yours-sync/events"
STATUS_PATH = "/api/yours-sync/status"
STORAGE_DIR = Path(
    os.environ.get("YOURS_BACKUP_DIR")
    or os.environ.get("YOURS_BACKUP_DATA_DIR")
    or "./yours-backups"
).resolve()
TOKEN = os.environ.get("YOURS_BACKUP_TOKEN", "").strip()
LATEST_BACKUP_NAME = "latest.zip"
LEGACY_LATEST_BACKUP_NAME = "yours-backup.zip"
PROTOCOL_VERSION = 2
IDENTITY_MODE = "syncId"
MAX_BACKUP_BYTES = int(os.environ.get("YOURS_BACKUP_MAX_BYTES", str(100 * 1024 * 1024)))
EVENT_LOCK = threading.Lock()


class BackupHandler(BaseHTTPRequestHandler):
    server_version = "YoursBackupServer/0.2"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/health", "/healthz"):
            self._send_text(HTTPStatus.OK, "ok\n")
            return
        if parsed.path == STATUS_PATH:
            self._handle_status()
            return
        if parsed.path == EVENTS_PATH:
            self._handle_events_download(parsed.query)
            return
        if parsed.path != BACKUP_PATH:
            self._send_text(HTTPStatus.NOT_FOUND, "not found\n")
            return
        if not self._authorized():
            return

        latest = _latest_backup()
        if latest is None:
            self._send_text(HTTPStatus.NOT_FOUND, "no backup\n")
            return

        data = latest.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{latest.name}"')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if self.path == EVENTS_PATH:
            self._handle_events_upload()
            return
        if self.path != BACKUP_PATH:
            self._send_text(HTTPStatus.NOT_FOUND, "not found\n")
            return
        if not self._authorized():
            return

        length = _content_length(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._send_text(HTTPStatus.BAD_REQUEST, "empty request\n")
            return
        if length > MAX_BACKUP_BYTES:
            self._send_text(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "backup is too large\n")
            return

        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        _filename, data = _extract_backup(content_type, body)
        if not data or not data.startswith(b"PK"):
            self._send_text(HTTPStatus.BAD_REQUEST, "backup must be a zip file\n")
            return
        if len(data) > MAX_BACKUP_BYTES:
            self._send_text(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "backup is too large\n")
            return

        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        output = STORAGE_DIR / LATEST_BACKUP_NAME
        _write_atomic(output, data)
        self._send_text(HTTPStatus.CREATED, f"uploaded {output.name}\n")

    def _handle_events_upload(self) -> None:
        if not self._authorized():
            return

        length = _content_length(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._send_text(HTTPStatus.BAD_REQUEST, "empty request\n")
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_text(HTTPStatus.BAD_REQUEST, "invalid json\n")
            return

        events = payload.get("events")
        if not isinstance(events, list):
            self._send_text(HTTPStatus.BAD_REQUEST, "events must be a list\n")
            return

        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        event_dir = STORAGE_DIR / "events"
        event_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        output = event_dir / f"yours-sync-events-{now.strftime('%Y%m%d')}.jsonl"
        stored = 0
        skipped = 0
        with EVENT_LOCK:
            next_seq = _latest_event_seq() + 1
            seen_event_ids = _event_ids()
            with output.open("a", encoding="utf-8") as handle:
                for event in events:
                    event_map = event if isinstance(event, dict) else {"payload": event}
                    event_id = event_map.get("eventId") or event_map.get("id")
                    if event_id is not None:
                        event_id = str(event_id)
                    entity_sync_id = event_map.get("entitySyncId")
                    if not isinstance(entity_sync_id, str) or ":" not in entity_sync_id:
                        self._send_text(HTTPStatus.BAD_REQUEST, "event entitySyncId is required\n")
                        return
                    if event_id and event_id in seen_event_ids:
                        skipped += 1
                        continue
                    server_seq = next_seq
                    next_seq += 1
                    stored += 1
                    if event_id:
                        seen_event_ids.add(event_id)
                    handle.write(
                        json.dumps(
                            {
                                "serverSeq": server_seq,
                                "receivedAt": now.isoformat(),
                                "client": payload.get("client", "yours"),
                                "eventId": event_id,
                                "deviceId": event_map.get("deviceId"),
                                "entityType": event_map.get("entityType"),
                                "entityId": event_map.get("entityId"),
                                "entitySyncId": entity_sync_id,
                                "action": event_map.get("action"),
                                "event": event_map,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )

        response = json.dumps(
            {
                "ok": True,
                "protocolVersion": PROTOCOL_VERSION,
                "identityMode": IDENTITY_MODE,
                "stored": stored,
                "skipped": skipped,
                "file": output.name,
                "latestCursor": _latest_event_seq(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(HTTPStatus.CREATED)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _handle_events_download(self, query: str) -> None:
        if not self._authorized():
            return

        params = parse_qs(query)
        try:
            after = int(params.get("after", ["0"])[0] or "0")
            limit = int(params.get("limit", ["500"])[0] or "500")
        except ValueError:
            self._send_text(HTTPStatus.BAD_REQUEST, "after and limit must be integers\n")
            return
        limit = max(1, min(limit, 1000))

        candidate_records = [record for record in _iter_event_records() if record["serverSeq"] > after]
        records = [record for record in candidate_records if _is_v2_event_record(record)]
        records = records[:limit]
        latest_cursor = _latest_event_seq()
        next_cursor = records[-1]["serverSeq"] if records else _max_record_seq(candidate_records, after)
        payload = {
            "ok": True,
            "protocolVersion": PROTOCOL_VERSION,
            "identityMode": IDENTITY_MODE,
            "events": records,
            "cursor": next_cursor,
            "latestCursor": latest_cursor,
            "hasMore": next_cursor < latest_cursor,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_status(self) -> None:
        if not self._authorized():
            return

        latest = _latest_backup()
        event_stats = _event_stats()
        payload = {
            "ok": True,
            "serverVersion": self.server_version,
            "protocolVersion": PROTOCOL_VERSION,
            "identityMode": IDENTITY_MODE,
            "authRequired": bool(TOKEN),
            "storageDir": str(STORAGE_DIR),
            "maxBackupBytes": MAX_BACKUP_BYTES,
            "eventCount": event_stats["count"],
            "latestCursor": event_stats["latestCursor"],
            "latestBackup": None,
            "message": "Yours self-hosted sync server is reachable.",
        }
        if latest is not None:
            stat = latest.stat()
            payload["latestBackup"] = {
                "filename": latest.name,
                "bytes": stat.st_size,
                "updatedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        if not TOKEN:
            return True
        expected = f"Bearer {TOKEN}"
        if self.headers.get("Authorization", "") == expected:
            return True
        self._send_text(HTTPStatus.UNAUTHORIZED, "unauthorized\n")
        return False

    def _send_text(self, status: HTTPStatus, text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _content_length(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _extract_backup(content_type: str, body: bytes) -> tuple[str, bytes]:
    if "multipart/form-data" not in content_type:
        return "latest.zip", body

    boundary_match = re.search(r"boundary=([^;]+)", content_type)
    if not boundary_match:
        return "", b""

    boundary = ("--" + boundary_match.group(1).strip('"')).encode("utf-8")
    for part in body.split(boundary):
        if b'name="backup"' not in part:
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        headers = part[:header_end].decode("utf-8", errors="ignore")
        data = part[header_end + 4 :].strip(b"\r\n-")
        filename_match = re.search(r'filename="([^"]+)"', headers)
        filename = filename_match.group(1) if filename_match else "latest.zip"
        return filename, data
    return "", b""


def _latest_backup() -> Path | None:
    if not STORAGE_DIR.exists():
        return None
    for filename in (LATEST_BACKUP_NAME, LEGACY_LATEST_BACKUP_NAME):
        explicit_latest = STORAGE_DIR / filename
        if explicit_latest.exists():
            return explicit_latest
    backups = sorted(STORAGE_DIR.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


def _write_atomic(output: Path, data: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=str(output.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output)
    finally:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass


def _event_files() -> list[Path]:
    event_dir = STORAGE_DIR / "events"
    if not event_dir.exists():
        return []
    return sorted(event_dir.glob("*.jsonl"))


def _iter_event_records() -> list[dict]:
    records: list[dict] = []
    fallback_seq = 0
    for event_file in _event_files():
        try:
            with event_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    fallback_seq += 1
                    server_seq = record.get("serverSeq")
                    if not isinstance(server_seq, int):
                        server_seq = fallback_seq
                        record["serverSeq"] = server_seq
                    records.append(record)
        except OSError:
            continue
    return sorted(records, key=lambda item: item["serverSeq"])


def _latest_event_seq() -> int:
    latest = 0
    for record in _iter_event_records():
        latest = max(latest, int(record.get("serverSeq", 0)))
    return latest


def _event_ids() -> set[str]:
    ids: set[str] = set()
    for record in _iter_event_records():
        event_id = record.get("eventId")
        if event_id is not None:
            ids.add(str(event_id))
    return ids


def _event_stats() -> dict[str, int]:
    records = _iter_event_records()
    latest = max((int(record.get("serverSeq", 0)) for record in records), default=0)
    return {"count": len(records), "latestCursor": latest}


def _is_v2_event_record(record: dict) -> bool:
    entity_sync_id = record.get("entitySyncId")
    if isinstance(entity_sync_id, str) and ":" in entity_sync_id:
        return True
    event = record.get("event")
    if isinstance(event, dict):
        event_entity_sync_id = event.get("entitySyncId")
        return isinstance(event_entity_sync_id, str) and ":" in event_entity_sync_id
    return False


def _max_record_seq(records: list[dict], fallback: int) -> int:
    latest = fallback
    for record in records:
        try:
            latest = max(latest, int(record.get("serverSeq", fallback)))
        except (TypeError, ValueError):
            continue
    return latest


def _event_count() -> int:
    return _event_stats()["count"]


def main() -> None:
    host = os.environ.get("YOURS_BACKUP_HOST", "0.0.0.0")
    port = int(os.environ.get("YOURS_BACKUP_PORT", "8088"))
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Backup server listening on http://{host}:{port}")
    print(f"Storage: {STORAGE_DIR}")
    ThreadingHTTPServer((host, port), BackupHandler).serve_forever()


if __name__ == "__main__":
    main()
