#!/usr/bin/env sh
set -eu

COMPOSE=""
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "Docker Compose is not available. Please install Docker first." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not available. Please install Docker first." >&2
  exit 1
fi

PORT="${YOURS_BACKUP_PORT:-8088}"
ENV_FILE=".env"

generate_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v uuidgen >/dev/null 2>&1; then
    uuidgen | tr '[:upper:]' '[:lower:]'
  else
    date +%s | sha256sum | awk '{print $1}'
  fi
}

detect_ip() {
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}' || true
  fi
}

if [ -f "$ENV_FILE" ]; then
  TOKEN="$(grep '^YOURS_BACKUP_TOKEN=' "$ENV_FILE" | sed 's/^YOURS_BACKUP_TOKEN=//' || true)"
  TOKEN="${TOKEN:-$(generate_token)}"
else
  TOKEN="$(generate_token)"
  cat > "$ENV_FILE" <<EOF
YOURS_BACKUP_HOST=0.0.0.0
YOURS_BACKUP_PORT=$PORT
YOURS_BACKUP_DIR=/data
YOURS_BACKUP_TOKEN=$TOKEN
YOURS_BACKUP_MAX_BYTES=104857600
EOF
fi

mkdir -p data

echo "Starting Yours Sync Server..."
$COMPOSE up -d

echo "Checking health..."
sleep 2
HEALTH_URL="http://127.0.0.1:$PORT/health"
STATUS_URL="http://127.0.0.1:$PORT/api/yours-sync/status"

if command -v curl >/dev/null 2>&1; then
  curl -fsS "$HEALTH_URL" >/dev/null
  curl -fsS -H "Authorization: Bearer $TOKEN" "$STATUS_URL" >/dev/null
else
  echo "curl is not available. Skipping automatic health check."
fi

LAN_IP="$(detect_ip)"
if [ -n "${LAN_IP:-}" ]; then
  SERVER_URL="http://$LAN_IP:$PORT"
else
  SERVER_URL="http://YOUR_SERVER_IP:$PORT"
fi

cat <<EOF

Yours Sync Server is ready.

Fill these values in Yours:

Server URL:
$SERVER_URL

API Key:
$TOKEN

App path:
Yours -> User -> Data Management -> Server Sync -> Settings

EOF
