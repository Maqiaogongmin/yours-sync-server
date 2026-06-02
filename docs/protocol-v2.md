# Protocol v2

Yours Sync Server v2 uses stable sync identity instead of local SQLite row ids.

## Status

`GET /api/yours-sync/status` returns:

```json
{
  "ok": true,
  "serverVersion": "YoursBackupServer/0.2",
  "protocolVersion": 2,
  "identityMode": "syncId",
  "authRequired": true,
  "eventCount": 12,
  "latestCursor": 12
}
```

## Identity

Each sync event must include:

```text
entitySyncId=<entityType>:<syncId>
```

Examples:

```text
routine:7b6e7c30-9c28-4d67-9df5-0cf0dd2b2c50
workout_session:aa7f26a7-0888-4e70-b698-f5664df71752
workout_log:cf984473-dc1d-4077-8d92-9208fe7e32e1
```

Local SQLite auto-increment ids are device-local implementation details. They must not be used as cross-device identity.

## Endpoints

- `GET /health`
- `GET /api/yours-sync/status`
- `GET /api/yours-sync/events?after=<cursor>&limit=<n>`
- `POST /api/yours-sync/events`
- `GET /api/yours-backups/latest`
- `POST /api/yours-backups/latest`

## Event Upload

`POST /api/yours-sync/events`

```json
{
  "schemaVersion": 2,
  "client": "yours",
  "events": [
    {
      "eventId": "device-event-id",
      "deviceId": "device-id",
      "entityType": "routine",
      "entitySyncId": "routine:uuid",
      "action": "update",
      "snapshot": {}
    }
  ]
}
```

Duplicate `eventId` values are skipped.

## Event Download

`GET /api/yours-sync/events?after=0&limit=500`

The server returns events after the cursor:

```json
{
  "ok": true,
  "protocolVersion": 2,
  "identityMode": "syncId",
  "events": [],
  "cursor": 0,
  "latestCursor": 0,
  "hasMore": false
}
```

The app should advance its local cursor only after downloaded events are applied successfully.
