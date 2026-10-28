from __future__ import annotations

from fastapi import HTTPException

ERROR_CODES = [
    "VALIDATION", "TOKEN_INVALID", "TOKEN_EXPIRED", "PENDING_INVALID",
    "INVALID_CODE", "BAD_CREDENTIALS", "EDUPAGE_2FA", "CAPTCHA_REQUIRED",
    "NOT_FOUND", "RATE_LIMITED", "CONFIG_MISSING", "UPSTREAM", "FORBIDDEN",
]

CODE_TEXT = {
    "VALIDATION": "Ungültige Eingabe.",
    "TOKEN_INVALID": "Token ungültig.",
    "TOKEN_EXPIRED": "Token abgelaufen.",
    "PENDING_INVALID": "Zwischen-Token ungültig oder abgelaufen.",
    "INVALID_CODE": "Ungültiger Code.",
    "BAD_CREDENTIALS": "Benutzername oder Passwort falsch.",
    "EDUPAGE_2FA": "EduPage verlangt eine erneute Anmeldung mit 2FA.",
    "CAPTCHA_REQUIRED": "EduPage verlangt ein Captcha.",
    "NOT_FOUND": "Nicht gefunden.",
    "RATE_LIMITED": "Zu viele Anfragen. Bitte später erneut versuchen.",
    "CONFIG_MISSING": "Server-Konfiguration fehlt.",
    "UPSTREAM": "EduPage-Fehler.",
    "FORBIDDEN": "Keine Berechtigung.",
}


def api_error(code: str, message: str | None = None, status: int | None = None) -> HTTPException:
    status_map = {
        "VALIDATION": 400, "TOKEN_INVALID": 401, "TOKEN_EXPIRED": 401,
        "PENDING_INVALID": 401, "INVALID_CODE": 401, "BAD_CREDENTIALS": 401,
        "EDUPAGE_2FA": 401, "CAPTCHA_REQUIRED": 403, "NOT_FOUND": 404,
        "RATE_LIMITED": 429, "CONFIG_MISSING": 500, "UPSTREAM": 502,
        "FORBIDDEN": 403,
    }
    sc = status or status_map.get(code, 400)
    return HTTPException(status_code=sc, detail={"error": message or CODE_TEXT.get(code, code), "code": code})
