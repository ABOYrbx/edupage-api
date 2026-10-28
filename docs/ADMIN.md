# Admin-Dashboard

## Ersteinrichtung

```bash
./scripts/install.sh     # venv, Abhängigkeiten, .env mit generiertem Passwort
./scripts/run.sh         # Backend :8787 + Frontend-Devserver :5173
```

`install.sh` legt `backend/.env` an (chmod 600) und füllt `ADMIN_PASSWORD` und
`CREDENTIAL_ENCRYPTION_KEY` mit Zufallswerten. **Beide Werte sicher verwahren** — ohne den
Vault-Key sind gespeicherte EduPage-Passwörter nicht mehr lesbar.

Danach `http://127.0.0.1:5173` öffnen und mit `admin` + Passwort aus der `.env` anmelden.

Produktiv (ein Prozess, FastAPI liefert das Frontend mit):

```bash
cd frontend && npm run build
./scripts/run.sh prod     # http://127.0.0.1:8787
```

## Konten

Ein Konto = eine EduPage-Identität (`<subdomain>.edupage.org` + Benutzername + Passwort).

1. **Konten → Konto hinzufügen**
2. Alias (optional), Subdomain (z. B. `login1` oder `gyk`), Benutzername, Passwort.
3. Antwort `status: ok` → Konto gespeichert und sofort nutzbar.
   Antwort `status: 2fa_required` → Code-Feld erscheint; Code innerhalb von 10 Minuten eingeben.
4. Fehler werden direkt angezeigt (`BAD_CREDENTIALS`, `CAPTCHA_REQUIRED`, `UPSTREAM`).

Spalte „Status“:

| Badge | Bedeutung |
| --- | --- |
| aktiv | letzter Login erfolgreich |
| Login fehlgeschlagen | Zugangsdaten falsch, gesperrt oder Captcha — `Testen` erneut versuchen |
| 2FA nötig | EduPage verlangt einen zweiten Faktor; Konto neu hinzufügen |

Aktionen pro Konto:

- **Keys** — zur Key-Verwaltung des Kontos springen.
- **Testen** — Login gegen EduPage prüfen, Status aktualisieren.
- **Cache leeren** — gecachte Daten und EduPage-Session verwerfen, dann neu einloggen.
- **Löschen** — entfernt Konto, Keys, Cache und Audit-Einträge (Passwort wird mit gelöscht).

Das Passwort steht nur verschlüsselt (AES-256-GCM) in der Datenbank und wird nur zum Login
entschlüsselt; es erscheint nie in Antworten, Logs oder im Dashboard.

## API-Keys

Ein Key gehört zu genau einem Konto. Agenten sehen nur die Daten dieses Kontos.

1. **API-Keys** → Konto wählen.
2. Name (z. B. „Claude Desktop“), Gültigkeit in Tagen (7/30/90/365 oder frei), optional
   **Schreibzugriff erlauben**.
3. Nach dem Erstellen wird der Voll-Key **genau einmal** angezeigt, inklusive fertigem
   `curl`-Beispiel. Danach zeigt die Liste nur noch das Prefix.

| Aktion | Wirkung |
| --- | --- |
| Rotieren | alter Key wird sofort ungültig, neuer mit gleichem Namen/Ablauf wird angezeigt |
| Widerrufen | Key gilt ab sofort nicht mehr (`401 TOKEN_INVALID`) |

Geht ein Key verloren: rotieren. Ohne `can_write` sind alle Schreib-Endpunkte gesperrt
(`403 FORBIDDEN`) — das ist der sichere Default für Lese-Agenten.

Spalte „Zuletzt benutzt“ zeigt, welcher Agent noch aktiv ist; abgelaufene Keys erkennt man am
Badge und am Datum.

## Aktivität

Jede Verwaltungsaktion wird protokolliert: Konto angelegt/getestet, Key erstellt/rotiert/
widerrufen. Filter nach Konto und Aktion, seitenweise (50 pro Seite).
Protokolliert werden nie Passwörter oder vollständige Keys — nur Prefixe und Namen.

## Einstellungen

- **Cache leeren** — alle zwischengespeicherten EduPage-Antworten verwerfen.
- **Funktionen** — zeigt, ob Wetter konfiguriert ist und ob Secure-Cookies aktiv sind.
- **System** — aktive Cache-TTLs und Limits. Diese Werte sind read-only; sie kommen aus
  `backend/.env` und werden beim Start gelesen.

## Passwort vergessen

```bash
cd backend
.venv/bin/python -m app.cli reset-admin                 # generiert ein neues Passwort
.venv/bin/python -m app.cli reset-admin --stdin         # interaktiv eingeben
```

Offene Admin-Sitzungen werden dabei abgemeldet. Weitere Befehle:

```bash
.venv/bin/python -m app.cli list-accounts   # Konten + Status
.venv/bin/python -m app.cli prune-cache     # abgelaufenen Cache/2FA-Vorgänge löschen
```

## Typische Fehler

| Anzeige | Ursache / Lösung |
| --- | --- |
| `Sitzung abgelaufen` | Admin-Session (8 h) abgelaufen → neu anmelden |
| `CSRF-Token ungültig` | Cookies im Browser löschen, neu anmelden |
| `EduPage verlangt ein Captcha` | EduPage sperrt den Login temporär; später erneut, ggf. im Browser einloggen |
| `CONFIG_MISSING` | `CREDENTIAL_ENCRYPTION_KEY` fehlt/ungültig oder Bibliothek nicht installiert |
| `UPSTREAM` | EduPage nicht erreichbar/geändert — Log des Backends prüfen |
