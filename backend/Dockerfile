# syntax=docker/dockerfile:1
# FabTrack API and worker image (same image, different command).
# Optional: --secret id=extra_ca,src=<ca-bundle.pem> when building behind a TLS-inspecting proxy.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/fabtrack

# WeasyPrint (PDF generation) needs Pango; fonts are bundled with the app, not downloaded.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.lock ./
COPY app ./app
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install -c requirements.lock .

COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd --system --uid 10001 --home-dir /srv/fabtrack fabtrack \
    && mkdir -p /data /srv/fabtrack/var \
    && chown -R fabtrack:fabtrack /data /srv/fabtrack/var
USER fabtrack

ENV FABTRACK_DATA_DIR=/data \
    FABTRACK_WORKER_HEARTBEAT_FILE=/srv/fabtrack/var/worker.heartbeat

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
