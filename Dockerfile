ARG PYTHON_IMAGE=python:3.12-alpine
FROM ${PYTHON_IMAGE}

LABEL org.opencontainers.image.title="Yours Sync Server"
LABEL org.opencontainers.image.description="Self-hosted sync server for Yours, a local-first training log app."
LABEL org.opencontainers.image.source="https://github.com/Maqiaogongmin/yours-sync-server"
LABEL org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY backup_server.py /app/backup_server.py

RUN adduser -D -H -u 10001 yours \
  && mkdir -p /data \
  && chown -R yours:yours /data /app

USER yours
EXPOSE 8088
CMD ["python", "/app/backup_server.py"]
