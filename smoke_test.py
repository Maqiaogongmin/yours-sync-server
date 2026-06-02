#!/usr/bin/env python3
"""Smoke test for a running Yours self-hosted sync server."""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.request
import uuid
import zipfile


def request(
    base_url: str,
    path: str,
    token: str,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
):
    url = base_url.rstrip("/") + path
    headers = {"Accept": "application/json, text/plain, */*"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        data = response.read()
        return response.status, response.headers, data


def expect_http_error(
    base_url: str,
    path: str,
    token: str,
    expected_status: int,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
) -> bytes:
    try:
        request(base_url, path, token, method=method, body=body, content_type=content_type)
    except urllib.error.HTTPError as error:
        data = error.read()
        assert error.code == expected_status
        return data
    raise AssertionError(f"Expected HTTP {expected_status} for {method} {path}")


def json_request(base_url: str, path: str, token: str, method: str = "GET", payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    status, _headers, data = request(
        base_url,
        path,
        token,
        method=method,
        body=body,
        content_type="application/json; charset=utf-8" if body is not None else None,
    )
    return status, json.loads(data.decode("utf-8"))


def make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", '{"format":"yours-backup","formatVersion":1}')
        archive.writestr("databases/local_training.sqlite", b"test")
        archive.writestr("databases/custom_exercises.sqlite", b"test")
    return buffer.getvalue()


def download_backup_if_present(base_url: str, token: str) -> bytes | None:
    try:
        status, _headers, data = request(base_url, "/api/yours-backups/latest", token)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    assert status == 200
    assert data.startswith(b"PK")
    return data


def upload_backup(base_url: str, token: str, data: bytes) -> int:
    status, _headers, _body = request(
        base_url,
        "/api/yours-backups/latest",
        token,
        method="POST",
        body=data,
        content_type="application/zip",
    )
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--token", default="change-me")
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Only verify health, auth, protocol, and event download shape. Do not upload events or backups.",
    )
    args = parser.parse_args()

    status, _headers, body = request(args.base_url, "/health", "", method="GET")
    assert status == 200 and body.strip() == b"ok"

    status, status_json = json_request(args.base_url, "/api/yours-sync/status", args.token)
    assert status == 200
    assert status_json["ok"] is True
    assert status_json["protocolVersion"] == 2
    assert status_json["identityMode"] == "syncId"
    if status_json.get("authRequired") is True:
        body = expect_http_error(args.base_url, "/api/yours-sync/status", args.token + "-wrong", 401)
        assert b"unauthorized" in body.lower()

    if args.read_only:
        status, events_json = json_request(args.base_url, "/api/yours-sync/events?after=0&limit=10", args.token)
        assert status == 200
        assert events_json["protocolVersion"] == 2
        assert events_json["identityMode"] == "syncId"
        assert "latestCursor" in events_json
        for record in events_json["events"]:
            entity_sync_id = record.get("entitySyncId")
            if not entity_sync_id and isinstance(record.get("event"), dict):
                entity_sync_id = record["event"].get("entitySyncId")
            assert isinstance(entity_sync_id, str) and ":" in entity_sync_id
        print("Yours sync read-only smoke test passed.")
        return 0

    run_id = str(uuid.uuid4())
    routine_sync_id = "11111111-1111-4111-8111-111111111111"
    event = {
        "eventId": f"smoke-device-{run_id}",
        "deviceId": "smoke-device",
        "entityType": "routine",
        "entityId": 1,
        "entitySyncId": f"routine:{routine_sync_id}",
        "action": "update",
        "snapshot": {
            "id": 1,
            "syncId": routine_sync_id,
            "name": "Smoke",
            "updatedAt": "2026-01-01T00:00:00",
        },
        "createdAt": "2026-01-01T00:00:00",
    }
    delete_event = {
        **event,
        "eventId": f"smoke-device-delete-{run_id}",
        "action": "delete",
        "createdAt": "2026-01-01T00:01:00",
    }
    bad_event_body = expect_http_error(
        args.base_url,
        "/api/yours-sync/events",
        args.token,
        400,
        method="POST",
        body=json.dumps({"events": [{**event, "entitySyncId": ""}]}).encode("utf-8"),
        content_type="application/json; charset=utf-8",
    )
    assert b"entitySyncId" in bad_event_body
    payload = {"schemaVersion": 2, "client": "smoke", "events": [event, event, delete_event]}
    status, upload_json = json_request(args.base_url, "/api/yours-sync/events", args.token, method="POST", payload=payload)
    assert status == 201
    assert upload_json["protocolVersion"] == 2
    assert upload_json["identityMode"] == "syncId"
    assert upload_json["stored"] == 2
    assert upload_json["skipped"] == 1

    status, events_json = json_request(args.base_url, "/api/yours-sync/events?after=0&limit=10", args.token)
    assert status == 200
    assert events_json["protocolVersion"] == 2
    assert events_json["identityMode"] == "syncId"
    assert "latestCursor" in events_json
    for record in events_json["events"]:
        entity_sync_id = record.get("entitySyncId")
        if not entity_sync_id and isinstance(record.get("event"), dict):
            entity_sync_id = record["event"].get("entitySyncId")
        assert isinstance(entity_sync_id, str) and ":" in entity_sync_id

    original_backup = download_backup_if_present(args.base_url, args.token)
    try:
        zip_bytes = make_zip()
        bad_zip_body = expect_http_error(
            args.base_url,
            "/api/yours-backups/latest",
            args.token,
            400,
            method="POST",
            body=b"this is not a zip",
            content_type="application/zip",
        )
        assert b"zip" in bad_zip_body.lower()

        assert upload_backup(args.base_url, args.token, zip_bytes) == 201

        status, headers, data = request(args.base_url, "/api/yours-backups/latest", args.token)
        assert status == 200
        assert headers.get_content_type() == "application/zip"
        assert data.startswith(b"PK")
    finally:
        if original_backup is not None:
            upload_backup(args.base_url, args.token, original_backup)

    print("Yours sync smoke test passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, urllib.error.URLError, urllib.error.HTTPError) as error:
        print(f"Smoke test failed: {error}", file=sys.stderr)
        raise SystemExit(1)
