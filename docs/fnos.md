# Feiniu / NAS Deployment

This guide assumes you already have Docker available on your NAS or Feiniu/fnOS device.

## Recommended Directory

Place the server in an app data directory:

```text
/home/YOUR_USER/docker/yours-sync
```

Recommended structure:

```text
yours-sync/
  docker-compose.yml
  .env
  data/
```

`data/` is the important directory. Back it up regularly.

## Install

```bash
git clone https://github.com/Maqiaogongmin/yours-sync-server.git
cd yours-sync-server
./install.sh
```

If Docker image downloads are slow, you can build locally:

```bash
PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-alpine docker build -t yours-sync-server .
```

Then update `docker-compose.yml` to use:

```yaml
image: yours-sync-server
```

## Permissions

If the container cannot write to `data/`:

```bash
mkdir -p data
sudo chown -R 10001:10001 data
```

## App Settings

Use the LAN address printed by `./install.sh`, for example:

```text
http://192.168.1.10:8088
```

Use the API key printed by `./install.sh`.
