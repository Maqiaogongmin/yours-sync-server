# Cloudflare Tunnel

Use Cloudflare Tunnel when you want to sync outside your home network without exposing plain HTTP directly to the public internet.

## Target

Forward your public HTTPS hostname to:

```text
http://127.0.0.1:8088
```

The app should use the public HTTPS address:

```text
https://yours-sync.example.com
```

Do not enter the Cloudflare dashboard URL, NAS admin URL, or Feiniu web UI URL in the app.

## Health Check

Open:

```text
https://yours-sync.example.com/health
```

It should return:

```text
ok
```

Then test the status API:

```bash
curl -H 'Authorization: Bearer YOUR_API_KEY' \
  https://yours-sync.example.com/api/yours-sync/status
```

The response should include `protocolVersion: 2` and `identityMode: syncId`.

## Common Problems

- HTTPS handshake failed: check certificate, tunnel status, and reverse proxy settings.
- HTML page returned: the hostname points to a web UI or default proxy page, not this sync server.
- 401 unauthorized: API key mismatch.
