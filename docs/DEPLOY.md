# Deployment

Der Dienst ist ein einzelner Prozess: FastAPI liefert API **und** Frontend-Build auf einem Port.

## Build

```bash
cd frontend && npm ci && npm run build     # -> frontend/dist
./scripts/run.sh prod                      # uvicorn auf HOST:PORT (Default 0.0.0.0:8787)
```

FastAPI erkennt `frontend/dist/index.html` beim Start und serviert die SPA samt Fallback für
Client-Routen (`/accounts`, `/keys`, …). Unbekannte `/api/...`-Pfade bleiben `404` mit
`{error, code}` statt HTML.

## Konfiguration

Alle Laufzeitwerte stehen in `backend/.env` (Vorlage: `backend/.env.example`). Pflicht:

| Variable | Bedeutung |
| --- | --- |
| `CREDENTIAL_ENCRYPTION_KEY` | 64 Hex-Zeichen; verschlüsselt die EduPage-Passwörter |
| `ADMIN_PASSWORD` | Initial-Passwort des Admins (nur beim ersten Start benutzt) |
| `DATABASE_URL` | Default `sqlite+aiosqlite:///./data/edupage-api.db` |

Wichtig: Der Vault-Key muss **fest** gesetzt sein. Ohne ihn generiert der Dienst bei jedem Start
einen neuen Schlüssel, und bereits gespeicherte Zugangsdaten sind nicht mehr entschlüsselbar.
Im Docker-Betrieb erledigt das der Entrypoint über `data/credential.key`; ohne Docker in
`backend/.env` eintragen.

Optional: `OPENWEATHER_API_KEY` (Wetter-Endpunkte), `COOKIE_SECURE=true` (hinter HTTPS),
`CORS_ORIGINS` (nur nötig, wenn ein Browser-Client von einer anderen Origin zugreift),
`AGENT_LIMIT`, `ADMIN_LOGIN_LIMIT`, `CACHE_TTL_*`, `SESSION_CACHE_TTL`.

## Docker

```bash
cp backend/.env.example .env    # optional; ohne .env wird ein Einmalpasswort geloggt
docker compose up -d --build
docker compose logs app | grep Einmalpasswort    # falls keine ADMIN_PASSWORD gesetzt war
```

Der Container:

- hört auf Port 8787 (`PORT` ändert nur die Host-Seite),
- bindet `./data` als Volume ein, damit SQLite-Datenbank **und** Vault-Key Neustarts überleben,
- startet als root, korrigiert dort die Rechte des Bind-Mounts (der gehört meist dem Host-User)
  und **wechselt dann auf uid 10001**, bevor die App läuft,
- legt beim ersten Start `data/credential.key` (Modus `600`) an, falls `CREDENTIAL_ENCRYPTION_KEY`
  nicht gesetzt ist. Der Schlüssel hat Vorrang, wenn die Variable gesetzt ist.

Der Vault-Key wird nur einmal erzeugt; bei späteren Starts liest der Entrypoint ihn aus der Datei.
**`data/` mit dem Key sichern** — ohne ihn sind die gespeicherten EduPage-Passwörter verloren.

Für Mehrbenutzerbetrieb ist Postgres vorkonfiguriert (auskommentiert) — dann `DATABASE_URL`
setzen und im Image `asyncpg` ergänzen (`pip install '.[postgres]'`).

## Reverse Proxy (Caddy)

```
edupage-api.example.com {
  reverse_proxy 127.0.0.1:8787
  encode zstd gzip
}
```

Bei HTTPS `COOKIE_SECURE=true` setzen, sonst sendet der Browser die Session-Cookies nicht.
Caddy terminiert TLS; der Dienst selbst muss kein Zertifikat kennen.

Nginx-Äquivalent:

```nginx
location / {
    proxy_pass http://127.0.0.1:8787;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 1m;
}
```

`X-Forwarded-For` wird für das Login-Rate-Limit ausgewertet — nur von einem vertrauenswürdigen
Proxy setzen lassen.

## Migrationen

Das Schema wird beim Start automatisch auf den neuesten Stand gebracht (Alembic, `alembic/versions`).
Manuell:

```bash
cd backend
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic revision --autogenerate -m "beschreibung"
```

Eine Datenbank aus der alten `create_all`-Phase (Tabellen ohne `alembic_version`) wird beim ersten
Start übernommen: fehlende Tabellen werden angelegt, dann wird auf `head` gestempelt — es gehen
keine Daten verloren. Ab dem zweiten Start laufen normale Migrationen.

## Worker-Anzahl

SQLite verträgt nur einen schreibenden Prozess: **ein** uvicorn-Worker (Default). Für mehrere
Worker Postgres verwenden:

```
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/edupage_api
```

## Backup

Alles, was zählt, liegt im Datenverzeichnis: DB **und** Vault-Key.

```bash
docker compose exec app sh -c 'sqlite3 /app/data/edupage-api.db ".backup /app/data/backup.db"'
# oder bei gestopptem Dienst das ganze Verzeichnis:
tar czf edupage-api-$(date +%F).tar.gz data/
```

Zur Wiederherstellung den Dienst stoppen, zurückkopieren, starten. **`data/credential.key`
gehört zwingend ins Backup**, sonst ist der gespeicherte Zugang wertlos.

## Betrieb prüfen

```bash
curl -fsS http://127.0.0.1:8787/api/v1/health        # {"status":"ok","version":"v1"}
curl -fsS -H "Authorization: Bearer $KEY" http://127.0.0.1:8787/api/v1/me
```

Logs gehen auf stdout/stderr (`docker compose logs -f app`). Passwörter und Keys werden nie
geloggt.

## Upgrades

```bash
git pull
docker compose up -d --build       # Image neu bauen, Migrationen laufen beim Start
```

Vorher `data/` sichern (DB + Vault-Key) und die `Release Notes` auf Schemaänderungen prüfen.
Ohne Docker:

```bash
cd frontend && npm ci && npm run build && cd ..
./scripts/run.sh prod
```
