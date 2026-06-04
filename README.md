# Yours Sync Server

Self-hosted sync server for **Yours**, a local-first training log app.

Yours does not provide an official cloud account system. This small server lets you sync training plans, archived plans, manual week marks, workout records, standard/free record modes, backup snapshots, and incremental change events through your own NAS, home server, VPS, or Feiniu/fnOS machine.

If you only want the simplest path, run the installer below, copy the printed server URL and API key, then paste them into Yours.

## Quick Start

```bash
git clone https://github.com/Maqiaogongmin/yours-sync-server.git
cd yours-sync-server
./install.sh
```

The installer will:

- check Docker and Docker Compose
- create `.env`
- generate an API key
- create `data/`
- start the server
- test `/health` and `/api/yours-sync/status`
- print the server URL and API key for the Yours app

In Yours, open:

```text
User -> Data Management -> Server Sync -> Settings
```

Fill in:

- Server URL: for example `http://192.168.1.10:8088`
- API Key: the value printed by `./install.sh`

Then tap `Test`, and tap `Sync Now`.

That is all most users need. The rest of this README is for manual Docker setup, remote access, backups, and troubleshooting.

## Manual Docker Compose Setup

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and replace the token:

```text
YOURS_BACKUP_TOKEN=replace-this-with-a-long-random-secret
```

Start the service:

```bash
docker compose up -d
```

Check health:

```bash
curl http://127.0.0.1:8088/health
```

Check the sync API:

```bash
curl -H 'Authorization: Bearer YOUR_API_KEY' \
  http://127.0.0.1:8088/api/yours-sync/status
```

The status response should include:

```json
{
  "protocolVersion": 2,
  "identityMode": "syncId"
}
```

## Data Directory

By default, Docker stores server data in:

```text
./data
```

Important files:

- `latest.zip`: latest full backup snapshot
- `events/*.jsonl`: incremental sync events

`events/*.jsonl` is not Yours Vault. Yours Vault is the app's reviewable folder export/import format. Server events are internal sync logs used by this service.

Back up the whole `data/` directory, not only `latest.zip`.

## HTTPS and Remote Access

Local network usage can use HTTP:

```text
http://192.168.1.10:8088
```

For internet access, do not expose plain HTTP directly. Use HTTPS through a reverse proxy or Cloudflare Tunnel.

See:

- [Feiniu / NAS guide](docs/fnos.md)
- [Cloudflare Tunnel guide](docs/cloudflare-tunnel.md)
- [Troubleshooting](docs/troubleshooting.md)

## Smoke Test

Run a full write test against a local server:

```bash
python3 smoke_test.py --base-url http://127.0.0.1:8088 --token YOUR_API_KEY
```

Run a read-only check against a live server:

```bash
python3 smoke_test.py --base-url https://your-domain.example --token YOUR_API_KEY --read-only
```

The full test covers health, protocol v2, auth failure, event upload/download, duplicate event dedupe, invalid zip rejection, and backup upload/download.

## Protocol

Current protocol:

- `protocolVersion: 2`
- `identityMode: syncId`

The app uses stable `syncId` values for cross-device identity. Local SQLite row IDs are not used as cross-device identity.

API endpoints:

- `GET /health`
- `GET /api/yours-sync/status`
- `GET /api/yours-sync/events?after=<cursor>&limit=<n>`
- `POST /api/yours-sync/events`
- `GET /api/yours-backups/latest`
- `POST /api/yours-backups/latest`

See [Protocol v2](docs/protocol-v2.md) for details.

## Security Notes

- Change the default API key.
- Do not publish `.env`.
- Do not expose plain HTTP to the public internet.
- Back up `data/` regularly.
- If the API key leaks, change `YOURS_BACKUP_TOKEN`, restart the service, and update the app settings.

## License

Apache-2.0
