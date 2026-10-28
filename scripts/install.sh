#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR/backend"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install -q -r <(grep -v '^#' /dev/stdin) <<'REQS'
fastapi>=0.115
uvicorn[standard]>=0.32
sqlalchemy[asyncio]>=2.0
aiosqlite>=0.20
alembic>=1.13
pydantic>=2.9
pydantic-settings>=2.6
python-multipart>=0.0.12
edupage-api>=0.13
cryptography>=43
argon2-cffi>=23.1
slowapi>=0.1.9
cachetools>=5.5
httpx>=0.27
python-dotenv>=1.0
pytest>=8
pytest-asyncio>=0.24
ruff>=0.7
REQS
mkdir -p data
if [ ! -f .env ]; then
  cp .env.example .env
  KEY=$(.venv/bin/python -c "import secrets; print(secrets.token_hex(32))")
  PW=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(16))")
  sed -i "s/^CREDENTIAL_ENCRYPTION_KEY=.*/CREDENTIAL_ENCRYPTION_KEY=$KEY/" .env
  sed -i "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$PW/" .env
  chmod 600 .env
  echo "Created .env with ADMIN_PASSWORD=$PW (save it!)"
fi
cd "$ROOT_DIR/frontend"
npm install
echo "Install complete."
