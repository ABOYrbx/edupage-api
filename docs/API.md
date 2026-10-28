# Agent-API (edupage-api)

Prefix `/api/v1`. Auth: `Authorization: Bearer <api-key>`.

Fehler immer `{error, code}`. Listen `{items, total, limit, offset}` (limit 50/max 200).

## Health
- `GET /health` → `{status:"ok", version:"v1"}` (ohne Auth)
- `GET /openapi.json`

## Endpoints (account-scoped über Key)
- `GET /me`
- `GET /messages` (?since, ?type, ?q, ?limit, ?offset, ?refresh)
- `GET /messages/{id}/thread`
- `POST /messages/read`
- `GET /recipients`
- `POST /messages/send` (nur can_write)
- `POST /messages/{id}/reply` (nur can_write)
- `POST /messages/download-token` `{event_id, idx}` → `{download_token, expires_in}`
- `GET /messages/{id}/attachments/{idx}` (?dl= / ?token=)
- `GET /homework`
- `POST /homework/{id}/done`, `/trash` (nur can_write)
- `GET /timetable/day?date=YYYY-MM-DD`
- `GET /timetable/week?date=YYYY-MM-DD`
- `GET /substitutions/week?date=YYYY-MM-DD`
- `GET /school/agenda`
- `GET /grades`
- `GET /wetter?city=...`
- `GET /wetter/suche?q=...`
- `GET /settings`, `PUT /settings` (nur can_write)
- `POST /cache-clear`

## Admin-API
Prefix `/api/v1/admin`, Cookie-Auth (epa_session) + CSRF (X-CSRF-Token).

- `POST /admin/login` `{username?, password}`
- `POST /admin/logout`
- `GET /admin/me`
- `GET/POST /admin/accounts`, `POST /admin/accounts/2fa`, `GET/DELETE /admin/accounts/{id}`, `POST /admin/accounts/{id}/test`, `/refresh`
- `GET/POST /admin/keys`, `POST /admin/keys/{id}/revoke`, `/rotate`
- `GET /admin/activity`
- `POST /admin/cache-clear`
- `GET/PUT /admin/settings`
