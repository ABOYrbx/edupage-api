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
