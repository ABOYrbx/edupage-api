# edupage-api

A standalone multi-account gateway for EduPage. A web UI manages several EduPage accounts, and
each account gets named API keys that you hand to AI agents (Claude, OpenClaw, …).
Through those keys agents can read messages, attachments, homework, timetables, grades, lunch
menus and school events — only for the account whose key they hold.

One process, one port, one SQLite file. No Node server in production, no external service.

## Quickstart

```bash
./scripts/install.sh      # venv, dependencies, .env with admin password + vault key
./scripts/run.sh          # dev: backend :8787 + frontend :5173
```

Dashboard: <http://127.0.0.1:5173> — sign in as `admin` with the password from `backend/.env`.

Production (FastAPI serves both API and frontend on one port):

```bash
cd frontend && npm ci && npm run build && cd ..
./scripts/run.sh prod     # http://127.0.0.1:8787
```

### Prebuilt image

Every release publishes a multi-arch image to GitHub Container Registry:

```bash
docker pull ghcr.io/aboyrbx/edupage-api:latest

docker run -d --name edupage-api \
  -p 8787:8787 \
  -e ADMIN_PASSWORD='change-me' \
  -v edupage-api-data:/app/data \
  ghcr.io/aboyrbx/edupage-api:latest
```

Dashboard: <http://127.0.0.1:8787>. The named volume keeps the SQLite database and
`credential.key`; **back it up**, otherwise the stored EduPage passwords are lost.

### With Docker Compose

```bash
cp backend/.env.example .env           # optional; ADMIN_PASSWORD recommended
docker compose up -d                   # pulls ghcr.io/aboyrbx/edupage-api:latest
docker compose logs app | grep Einmalpasswort   # only without ADMIN_PASSWORD
```

Pin a release with `IMAGE_TAG=0.1.0 docker compose up -d`. To build from source instead,
uncomment `build: .` in `docker-compose.yml` and run `docker compose up -d --build`.

On first start the container creates `data/credential.key` and keeps it across restarts —
**back this directory up**, otherwise the stored EduPage passwords are lost.

## Agent access in three steps

1. **Add an account** — Dashboard → Accounts → subdomain (`login1`, `gyk`, …), username and
   password. If two-factor authentication is enabled, the dashboard asks for the code right away.
2. **Create a key** — Dashboard → API Keys → account, name, expiry, optionally write access.
   The full key is shown **exactly once**.
3. **Use it from an agent**:

```bash
curl -H "Authorization: Bearer epk_..." http://127.0.0.1:8787/api/v1/homework?status=offen
```

```bash
curl -H "Authorization: Bearer epk_..." http://127.0.0.1:8787/api/v1/messages?limit=5
curl -H "Authorization: Bearer epk_..." http://127.0.0.1:8787/api/v1/timetable/week
curl -H "Authorization: Bearer epk_..." http://127.0.0.1:8787/api/v1/grades
```

## Security at a glance

- EduPage passwords are stored AES-256-GCM encrypted in the database and never returned by the API.
- API keys are stored as SHA-256 hashes only; the plaintext is displayed once.
- Admin login: Argon2id, session as an httpOnly cookie (8 h) with CSRF double-submit, rate limited.
- Agent keys are **read-only** by default; write access must be granted per key.
- Per-key rate limiting, short-lived download tokens (5 min) for attachments instead of long-lived links.

## Documentation

The docs are currently written in German.

| File | Contents |
| --- | --- |
| [`docs/API.md`](docs/API.md) | Agent API: endpoints, formats, error codes, examples |
| [`docs/ADMIN.md`](docs/ADMIN.md) | Dashboard: accounts, keys, activity, password reset |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Docker, reverse proxy, HTTPS, migrations, backup |

Interactive API docs ship with the app: <http://127.0.0.1:8787/docs> · OpenAPI: `/api/v1/openapi.json`.

## Development

```bash
cd backend && .venv/bin/python -m pytest -q     # offline, fake EduPage provider
cd frontend && npm run typecheck && npm run build
```

Agent-oriented notes live in [`AGENTS.md`](AGENTS.md). The backend uses the
[`edupage-api`](https://github.com/EdupageAPI/edupage-api) library (GPL-3.0) for the EduPage
protocol; this project is intended for personal use.
