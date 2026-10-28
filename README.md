# edupage-api

Standalone Multi-Account-Gateway für EduPage — eine Web-UI verwaltet mehrere EduPage-Konten,
jedes Konto bekommt benannte API-Keys, die du an KI-Agenten (Claude, OpenClaw, …) gibst.
Die Agenten lesen damit Nachrichten, Anhänge, Hausaufgaben, Stundenplan, Noten, Speiseplan und
Termine — nur für das Konto, dessen Key sie haben.

Ein Prozess, ein Port, eine SQLite-Datei. Kein Node-Server in Produktion, kein externer Dienst.

## Quickstart

```bash
./scripts/install.sh      # venv, Abhängigkeiten, .env mit Admin-Passwort + Vault-Key
./scripts/run.sh          # Dev: Backend :8787 + Frontend :5173
```

Dashboard: <http://127.0.0.1:5173> — Anmeldung als `admin` mit dem Passwort aus `backend/.env`.

Produktiv (FastAPI liefert API und Frontend auf einem Port):

```bash
cd frontend && npm ci && npm run build && cd ..
./scripts/run.sh prod     # http://127.0.0.1:8787
```

Mit Docker:

```bash
cp backend/.env.example .env           # optional; ADMIN_PASSWORD empfohlen
docker compose up -d --build
docker compose logs app | grep Einmalpasswort   # nur ohne ADMIN_PASSWORD
```

Der Container legt beim ersten Start `data/credential.key` an und behält ihn über Neustarts —
**dieses Verzeichnis sichern**, sonst sind die gespeicherten EduPage-Passwörter verloren.

## In drei Schritten zum Agenten-Zugriff

1. **Konto hinzufügen** — Dashboard → Konten → Subdomain (`login1`, `gyk`, …), Benutzername und
   Passwort. Bei aktivierter Zwei-Faktor-Anmeldung fragt das Dashboard direkt nach dem Code.
2. **Key erstellen** — Dashboard → API-Keys → Konto, Name, Gültigkeit, optional Schreibzugriff.
   Der vollständige Key wird **genau einmal** angezeigt.
3. **Agent nutzen**:

```bash
curl -H "Authorization: Bearer epk_..." http://127.0.0.1:8787/api/v1/homework?status=offen
```

```bash
curl -H "Authorization: Bearer epk_..." http://127.0.0.1:8787/api/v1/messages?limit=5
curl -H "Authorization: Bearer epk_..." http://127.0.0.1:8787/api/v1/timetable/week
curl -H "Authorization: Bearer epk_..." http://127.0.0.1:8787/api/v1/grades
```

## Sicherheit im Kurzüberblick

- EduPage-Passwörter liegen AES-256-GCM-verschlüsselt in der Datenbank und werden nie ausgeliefert.
- API-Keys werden nur als SHA-256-Hash gespeichert; angezeigt wird der Klartext einmalig.
- Admin-Login: Argon2id, Sitzung als httpOnly-Cookie (8 h) mit CSRF-Double-Submit, Rate-Limit.
- Agenten-Keys sind standardmäßig **nur lesend**; Schreiben muss pro Key freigegeben werden.
- Rate-Limit pro Key, kurze Download-Tokens (5 Min) für Anhänge statt langlebiger Links.

## Dokumentation

| Datei | Inhalt |
| --- | --- |
| [`docs/API.md`](docs/API.md) | Agent-API: Endpunkte, Formate, Fehlercodes, Beispiele |
| [`docs/ADMIN.md`](docs/ADMIN.md) | Dashboard: Konten, Keys, Aktivität, Passwort-Reset |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Docker, Reverse Proxy, HTTPS, Migrationen, Backup |

Interaktive API-Doku läuft mit: <http://127.0.0.1:8787/docs> · OpenAPI: `/api/v1/openapi.json`.

## Entwicklung

```bash
cd backend && .venv/bin/python -m pytest -q     # offline, Fake-EduPage-Provider
cd frontend && npm run typecheck && npm run build
```

Hinweise für Agenten stehen in [`AGENTS.md`](AGENTS.md). Das Backend nutzt die
[`edupage-api`](https://github.com/EdupageAPI/edupage-api)-Bibliothek (GPL-3.0) für das
EduPage-Protokoll; dieses Projekt ist für den privaten Gebrauch gedacht.
