# Agent-API (edupage-api)

Basis: `http://<host>:8787/api/v1`

## Authentifizierung

Jeder Agent nutzt einen **API-Key pro EduPage-Konto**, den der Admin im Dashboard erstellt.
Der Key bestimmt das Konto — es gibt keinen Konto-Parameter in der URL.

```
Authorization: Bearer epk_xxxxxxxxxxxxxxxxxxxxxxxx
```

Alternativ (nur für Links, z. B. Anhang-Downloads): `?token=epk_...`

Eigenschaften:

- Key wird **genau einmal** bei der Erstellung angezeigt, gespeichert wird nur sein SHA-256-Hash.
- Ablauf (`expires_in_days`) und Widerruf sind jederzeit möglich; ein widerrufener Key gilt sofort nicht mehr.
- `can_write=false` (Default): alle schreibenden Endpunkte antworten mit `403 FORBIDDEN`.
- Rate-Limit pro Key: `AGENT_LIMIT` (Default 120/Minute) → `429 RATE_LIMITED`.

## Antwortformat

Listen sind immer paginiert:

```json
{ "items": [...], "total": 128, "limit": 50, "offset": 0 }
```

`limit` Default 50, Maximum 200; `offset` ≥ 0. Ungültige Werte → `400 VALIDATION`.

Fehler sind immer `{ "error": "<Menschentext>", "code": "<CODE>" }`.

| Code | HTTP | Bedeutung |
| --- | --- | --- |
| `VALIDATION` | 400 | Parameter ungültig |
| `TOKEN_INVALID` | 401 | Key fehlt, unbekannt oder widerrufen |
| `TOKEN_EXPIRED` | 401 | Key abgelaufen |
| `FORBIDDEN` | 403 | Schreibzugriff auf einem Nur-Lese-Key |
| `CAPTCHA_REQUIRED` | 403 | EduPage verlangt ein Captcha (nur Admin-Flows) |
| `NOT_FOUND` | 404 | Objekt existiert nicht |
| `RATE_LIMITED` | 429 | Zu viele Anfragen |
| `CONFIG_MISSING` | 500/503 | Server-Konfiguration unvollständig (z. B. kein Wetter-Key) |
| `UPSTREAM` | 502 | EduPage hat nicht wie erwartet geantwortet |

Caching: Antworten werden pro Konto gecacht (Nachrichten 15 Min, Noten/Stundenplan 60 Min,
Speiseplan 15 Min). Ein Feld `"cache": "memory" | "db" | "miss"` zeigt die Herkunft.
`?refresh=1` erzwingt einen Upstream-Abruf.

## Endpunkte

Alle Endpunkte sind kontogebunden; „Schreiben“ bedeutet `can_write=true` erforderlich.

### Meta

| Methode | Pfad | Beschreibung |
| --- | --- | --- |
| GET | `/health` | `{status, version}` — ohne Auth |
| GET | `/openapi.json` | OpenAPI 3 — ohne Auth |
| GET | `/me` | Konto + Key hinter dem Bearer-Token |

`GET /me` → `{subdomain, username, alias, key: {id, name, prefix, can_write}}`

### Nachrichten

| Methode | Pfad | Parameter / Body |
| --- | --- | --- |
| GET | `/messages` | `since=YYYY-MM-DD`, `type`, `q`, `limit`, `offset`, `refresh=1` |
| GET | `/messages/{event_id}/thread` | `refresh=1` |
| POST | `/messages/read` | `{event_ids: [1, 2]}` *(Schreiben)* |
| GET | `/recipients` | — |
| POST | `/messages/send` | `{recipients: ["Frau Muster"], body: "Text"}` *(Schreiben)* |
| POST | `/messages/{event_id}/reply` | `{body: "Text"}` *(Schreiben)* |
| POST | `/messages/download-token` | `{event_id, idx}` → `{download_token, expires_in: 300}` |
| GET | `/messages/{event_id}/attachments/{idx}` | `?dl=<download_token>` oder Bearer |

Nachrichten-Objekt:

```json
{
  "id": 1234,
  "timestamp": "Heute · 08:15",
  "timestamp_iso": "2026-10-28T08:15:00",
  "sort_key": "2026-10-28T08:15:00",
  "author": "Frau Muster",
  "recipient": "Max Mustermann",
  "type": "sprava",
  "type_label": "Nachricht",
  "text": "Elternabend am Freitag",
  "is_starred": false,
  "is_done": false,
  "reaction_count": 0,
  "extra": "{ ... Rohdaten als JSON-String ... }",
  "attachments": [{ "name": "plan.pdf", "url": "/files/plan.pdf" }]
}
```

`type` filtert auf den Roh-Typ (`sprava`, `homework`, `sexam`, `event`, …), `type_label` ist die
deutsche Bezeichnung. `extra` enthält die vollständige EduPage-Rohstruktur für Details.

`/recipients` → `[{id, name, kind}]` (`kind`: `teacher` / `student`).

Anhang-Download in zwei Schritten (empfohlen — der API-Key landet so nicht in Logs):

```bash
TOKEN=$(curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"event_id": 1234, "idx": 0}' "$API/messages/download-token" | jq -r .download_token)
curl -OJ "$API/messages/1234/attachments/0?dl=$TOKEN"
```

Der Download-Token gilt 300 s, ist an Konto + Event + Anhang gebunden und einmalig verwendbar.

### Hausaufgaben

| Methode | Pfad | Parameter / Body |
| --- | --- | --- |
| GET | `/homework` | `since`, `status`, `include_tests=1`, `q`, `limit`, `offset` |
| POST | `/homework/{id}/done` | `{done: true}` *(Schreiben)* |
| POST | `/homework/{id}/trash` | `{hide: true}` *(Schreiben)* |

`status`: `alle` (Default), `offen`, `heute fällig`, `überfällig`, `erledigt`, `ohne Datum`.
`include_tests=1` nimmt Prüfungen/Tests mit auf.

`/homework/{id}/trash` ist **rein lokal**: EduPage kennt keinen Papierkorb, deshalb merkt sich
das Gateway das Verstecken in der eigenen Datenbank (`hide: false` holt die Aufgabe zurück).
In EduPage wird dabei nichts geändert; `done` bleibt die einzige Aktion, die dorthin schreibt.

Die Antwort enthält zusätzlich `counts`: `{offen, ueberfaellig, erledigt}` (immer über alle
Hausaufgaben, unabhängig vom `status`-Filter). Sortierung: überfällig → offen → erledigt.

```json
{
  "id": 77, "type": "homework", "type_label": "Hausaufgabe",
  "title": "Seite 12, Aufgabe 3", "description": "…", "subject": "Mathe",
  "author": "Herr Beispiel", "recipient": "Max Mustermann",
  "assigned": "2026-10-26 14:00", "assigned_iso": "2026-10-26T14:00:00",
  "due": "2026-10-29", "due_display": "Do 29.10.2026", "due_raw": "2026-10-29",
  "status": "offen", "is_done": false, "done_at": "", "is_starred": false,
  "extra": "{ ... }"
}
```

### Stundenplan & Vertretungen

| Methode | Pfad | Parameter |
| --- | --- | --- |
| GET | `/timetable/day` | `date=YYYY-MM-DD` (Default: heute) |
| GET | `/timetable/week` | `date=YYYY-MM-DD` (Starttag, 7 Tage) |
| GET | `/substitutions/week` | `date=YYYY-MM-DD` |

`/timetable/day` → `{date, lessons: [...]}`; `/timetable/week` → Liste von 7 solchen Tagen
(Wochenenden sind leer und lösen keinen Upstream-Abruf aus).

### Schule & Noten

| Methode | Pfad | Beschreibung |
| --- | --- | --- |
| GET | `/school/agenda` | Termine (Events, Ausflüge, Feiertage, Elternabende, …) |
| GET | `/grades` | Noten (gecacht 60 Min) |
| GET | `/lunches` | Speiseplan, `date=YYYY-MM-DD` (Default: heute) |
| GET | `/settings` | Konto-/Schul-Stammdaten |
| POST | `/cache-clear` | Cache dieses Kontos leeren |

`/lunches` → `{date, snack, lunch, afternoon_snack, cache}`; jeder Gang ist `null` oder
`{title, type, served_from, served_to, chooseable_menus, ordered_meal, menus: [{name, allergens, weight, number}]}`.

### Wetter (optional)

| Methode | Pfad | Parameter |
| --- | --- | --- |
| GET | `/wetter` | `city=Berlin` **oder** `lat=52.5&lon=13.4` |
| GET | `/wetter/suche` | `q=Ber` (mind. 2 Zeichen) |

Benötigt `OPENWEATHER_API_KEY` in der `.env`; sonst `503 CONFIG_MISSING`.
Der Key bleibt serverseitig.

## Admin-API

Prefix `/api/v1/admin`. Auth über httpOnly-Cookie `epa_session` (8 h) **plus** CSRF-Double-Submit:
bei `POST`/`PUT`/`PATCH`/`DELETE` muss der Header `X-CSRF-Token` dem Cookie `epa_csrf` entsprechen.

| Methode | Pfad | Body / Hinweis |
| --- | --- | --- |
| POST | `/login` | `{username?, password}` → setzt beide Cookies |
| POST | `/logout` | widerruft die Session |
| GET | `/me` | `{username}` |
| GET/POST | `/accounts` | Liste / `{alias?, subdomain, username, password}` |
| POST | `/accounts/2fa` | `{pending_token, code}` — schließt einen 2FA-Login ab |
| GET/DELETE | `/accounts/{id}` | Detail inkl. Keys / löschen (Cascade) |
| POST | `/accounts/{id}/test` | Login testen, `status` aktualisieren |
| POST | `/accounts/{id}/refresh` | Cache + Session leeren und neu einloggen |
| GET | `/keys?account={id}` | Keys (nie der Voll-Key) |
| POST | `/keys` | `{account_id, name, expires_in_days?, can_write?}` → Voll-Key **einmalig** |
| POST | `/keys/{id}/revoke` | widerrufen |
| POST | `/keys/{id}/rotate` | alten widerrufen, neuen ausstellen |
| GET | `/activity` | `account`, `action`, `limit`, `offset` |
| POST | `/cache-clear` | `{account_id?}` — global oder pro Konto |
| GET | `/settings` | Laufzeitwerte (read-only, aus der `.env`) |

Konto hinzufügen mit 2FA: `POST /accounts` antwortet dann mit
`{status: "2fa_required", pending_token, pending_expires_in: 600}`; den Code innerhalb von
10 Minuten an `POST /accounts/2fa` schicken.
