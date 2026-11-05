#!/usr/bin/env bash
# Build the offline release bundle: Docker images (docker save), compose file,
# .env template and SHA-256 checksums. Install on a machine with no internet
# using `docker load -i images.tar` (see INSTALL.txt inside the bundle).
#
# Optional: EXTRA_CA=/path/to/ca.pem when the build machine sits behind a TLS-inspecting proxy.
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=$(backend/.venv/bin/python -c "import sys; sys.path.insert(0, 'backend'); import app; print(app.__version__)")
OUT="dist/fabtrack-${VERSION}"
POSTGRES_IMAGE="pgvector/pgvector:pg16"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not reachable; packaging needs Docker." >&2
  exit 1
fi

secret_args=()
if [[ -n "${EXTRA_CA:-}" ]]; then
  secret_args=(--secret "id=extra_ca,src=${EXTRA_CA}")
fi

echo "==> Building images for ${VERSION}"
docker build "${secret_args[@]}" -t "fabtrack/api:${VERSION}" backend
docker build "${secret_args[@]}" --build-context deploy=deploy -t "fabtrack/web:${VERSION}" frontend
docker pull "${POSTGRES_IMAGE}"

echo "==> Writing bundle to ${OUT}"
mkdir -p "${OUT}"
docker save -o "${OUT}/images.tar" \
  "fabtrack/api:${VERSION}" "fabtrack/web:${VERSION}" "${POSTGRES_IMAGE}"
cp deploy/docker-compose.yml "${OUT}/"
sed "s/^FABTRACK_VERSION=.*/FABTRACK_VERSION=${VERSION}/" deploy/.env.example > "${OUT}/.env.example"
# The bundle runs prebuilt images only: drop build sections so compose never tries to build.
backend/.venv/bin/python - "${OUT}/docker-compose.yml" <<'PY'
import re
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
text = re.sub(r"\n    build:\n(?:      .*\n|        .*\n)+", "\n", text)
open(path, "w", encoding="utf-8").write(text)
PY
cat > "${OUT}/INSTALL.txt" <<EOF
FabTrack ${VERSION} offline bundle

1. Verify:   sha256sum -c SHA256SUMS
2. Load:     docker load -i images.tar
3. Configure: cp .env.example .env   (set POSTGRES_PASSWORD and FABTRACK_SECRET_KEY=\$(openssl rand -hex 32))
4. Start:    docker compose --env-file .env up -d --wait
5. Open:     http://<server>:8080  (port: FABTRACK_HTTP_PORT)
EOF
(cd "${OUT}" && sha256sum images.tar docker-compose.yml .env.example INSTALL.txt > SHA256SUMS)
tar -C dist -cf "dist/fabtrack-${VERSION}.tar" "fabtrack-${VERSION}"
(cd dist && sha256sum "fabtrack-${VERSION}.tar" > "fabtrack-${VERSION}.tar.sha256")
echo "==> Done: dist/fabtrack-${VERSION}.tar"
