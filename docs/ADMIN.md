# Admin-Dashboard

1. `./scripts/install.sh` (legt `.env` mit Admin-Passwort an).
2. `./scripts/run.sh` → Backend :8787, Frontend Dev :5173.
3. Login mit Passwort aus `.env`.
4. Konto hinzufügen (Subdomain + Username + Passwort; bei 2FA Code eingeben).
5. Key erstellen (Name, Ablauf, Schreibzugriff). Voll-Key wird einmal angezeigt → kopieren.
6. Key an Agent weitergeben: `Authorization: Bearer <key>`.
