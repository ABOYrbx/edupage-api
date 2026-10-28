#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR/backend"

if [ ! -d .venv ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 .venv
  else
    python3 -m venv .venv
  fi
fi

# uv-created venvs have no pip; prefer uv so both flavours work.
if command -v uv >/dev/null 2>&1; then
  uv pip install --python .venv/bin/python -q -e '.[dev]'
elif .venv/bin/python -m pip --version >/dev/null 2>&1; then
  .venv/bin/python -m pip install -q -e '.[dev]'
else
  echo "Weder uv noch pip im venv gefunden. Bitte 'uv' installieren oder .venv neu anlegen." >&2
  exit 1
fi

mkdir -p data

if [ ! -f .env ]; then
  cp .env.example .env
  KEY=$(.venv/bin/python -c "import secrets; print(secrets.token_hex(32))")
  PW=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(16))")
  .venv/bin/python - "$KEY" "$PW" <<'PY'
import pathlib, sys
key, pw = sys.argv[1], sys.argv[2]
path = pathlib.Path(".env")
lines = []
for line in path.read_text().splitlines():
    if line.startswith("CREDENTIAL_ENCRYPTION_KEY="):
        line = f"CREDENTIAL_ENCRYPTION_KEY={key}"
    elif line.startswith("ADMIN_PASSWORD="):
        line = f"ADMIN_PASSWORD={pw}"
    lines.append(line)
path.write_text("\n".join(lines) + "\n")
PY
  chmod 600 .env
  echo
  echo "backend/.env angelegt."
  echo "  ADMIN_PASSWORD=$PW"
  echo "  CREDENTIAL_ENCRYPTION_KEY=$KEY"
  echo "Beides sichern - der Vault-Key ist noetig, um gespeicherte Zugangsdaten zu lesen."
  echo
fi

echo "Datenbank migrieren ..."
.venv/bin/python -m alembic upgrade head

cd "$ROOT_DIR/frontend"
npm install
echo
echo "Installation abgeschlossen. Start: ./scripts/run.sh"
