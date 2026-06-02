# Troubleshooting

## App Test Failed

First test from the server:

```bash
curl http://127.0.0.1:8088/health
```

Then test from another machine on the same network:

```bash
curl http://SERVER_LAN_IP:8088/health
```

If the first works but the second fails, check firewall, port mapping, NAS networking, or router isolation.

## 401 unauthorized

The API key is wrong.

Check that the app API key exactly matches `YOURS_BACKUP_TOKEN` in `.env`.

## 404 no backup

The server has no backup snapshot yet.

Use the device with the latest data, configure server sync, and tap `Sync Now`.

## HTML Page Returned

The server URL is pointing to the wrong service, usually a NAS admin page, Feiniu web UI, or reverse proxy default page.

The correct base URL should return `ok` at `/health`.

## HTTPS Handshake Failed

Check:

- domain certificate
- reverse proxy target
- Cloudflare Tunnel status
- whether the current network blocks the connection

## backup must be a zip file

The uploaded body is not a Yours backup zip. Normal app sync should not produce this error.

## Server Version Too Old

Newer Yours builds require:

- `protocolVersion: 2`
- `identityMode: syncId`

Update this server and restart the container.
