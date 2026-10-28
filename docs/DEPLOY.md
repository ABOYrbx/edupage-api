# Deployment

## Produktion (ein Prozess)
```bash
cd frontend && npm run build   # baut nach frontend/dist
cd ../backend && ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8787
```
FastAPI serviert das Frontend-Build automatisch aus `frontend/dist`.

## Reverse Proxy (Caddy)
```
edupage-api.example.com {
  reverse_proxy 127.0.0.1:8787
}
```
Setze `CORS_ORIGINS` und aktiviere Secure-Cookies (Code-Anpassung nötig für HTTPS).

## Backup
SQLite-Datei `backend/data/edupage-api.db` kopieren (bei gestopptem Service oder mit `.backup`).
