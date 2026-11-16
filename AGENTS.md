# edupage-api — Hinweise für Agenten

Eigenständiger Multi-Account-Gateway für EduPage, optimiert für KI-Agenten.

## Regeln
- Gehe NIEMALS an `.env`, `.env.*`, `data/`, `*.db*` oder Logs. Keine Secrets lesen/loggen/committen.
- Backend: FastAPI + SQLAlchemy (async) + SQLite (Default). Frontend: React + Vite + Tailwind.
- Tests laufen offline (pytest, Fake-Provider). `cd backend && .venv/bin/python -m pytest -q` muss grün bleiben.
- Typecheck Frontend: `cd frontend && npm run typecheck`.

## Struktur
- backend/app — FastAPI-App
- frontend/src — React-SPA
- scripts/install.sh, scripts/run.sh
- docs/ — API.md, ADMIN.md, DEPLOY.md

## Konventionen
- Fehler immer `{error, code}` mit kanonischem Vokabular (siehe core/errors.py).
- Listen immer `{items, total, limit, offset}`.
- Keys werden nur bei Erstellung im Klartext zurückgegeben.

## Release
- Tag `v*` pushen (z. B. `git tag -a v0.1.1 -m v0.1.1 && git push origin v0.1.1`).
- `.github/workflows/release.yml` baut `linux/amd64` + `linux/arm64`, pusht nach
  `ghcr.io/aboyrbx/edupage-api` und erstellt das GitHub-Release.
- Image-Tags: `X.Y.Z`, `X.Y`, `latest`, `sha-<commit>`.
- Vor dem Tag muss der Build lokal grün sein; der Workflow prüft zusätzlich
  `/api/v1/health` im gestarteten Image.

