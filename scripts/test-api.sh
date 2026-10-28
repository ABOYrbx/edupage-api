#!/usr/bin/env sh
# Rauchtet die Agent-API gegen eine laufende Instanz.
#
#   ./scripts/test-api.sh                          # fragt den Key ab (Eingabe unsichtbar)
#   EDUPAGE_KEY=epk_... ./scripts/test-api.sh      # Key aus der Umgebung
#   EDUPAGE_API=http://host:8787/api/v1 ./scripts/test-api.sh
#
# Der Key wird nie ausgegeben und nie in eine Datei geschrieben.
set -eu

API=${EDUPAGE_API:-http://127.0.0.1:8787/api/v1}
KEY=${EDUPAGE_KEY:-}

if [ -z "$KEY" ]; then
  printf 'API-Key (epk_...): ' >&2
  stty -echo 2>/dev/null || true
  IFS= read -r KEY
  stty echo 2>/dev/null || true
  printf '\n' >&2
fi

if [ -z "$KEY" ]; then
  echo "Kein Key angegeben." >&2
  exit 2
fi

command -v curl >/dev/null 2>&1 || { echo "curl fehlt." >&2; exit 2; }

# tmp-Datei statt -w, damit Status und Body gemeinsam ausgewertet werden koennen
BODY=$(mktemp)
trap 'rm -f "$BODY"' EXIT

call() {
  label=$1
  path=$2
  status=$(curl -sS -o "$BODY" -w '%{http_code}' -H "Authorization: Bearer $KEY" "$API$path" || true)
  if [ "$status" = "200" ]; then
    printf '  ok    %-38s %s\n' "$label" "$(head -c 110 "$BODY" | tr -d '\n')"
  else
    printf '  FEHLER %-37s HTTP %s  %s\n' "$label" "$status" "$(head -c 160 "$BODY" | tr -d '\n')"
  fi
}

echo "Ziel: $API"
echo

echo "Verbindung und Key"
call "/health" "/health"
call "/me" "/me"

echo
echo "Lesedaten"
call "/messages?limit=3" "/messages?limit=3"
call "/homework?status=offen" "/homework?status=offen"
call "/timetable/day" "/timetable/day"
call "/grades" "/grades"
call "/lunches" "/lunches"
call "/school/agenda" "/school/agenda"

echo
echo "Erwartete Fehler"
# ohne Auth muss 401 kommen
status=$(curl -sS -o "$BODY" -w '%{http_code}' "$API/me" || true)
printf '  %s  ohne Key -> HTTP %s (erwartet 401)\n' "$([ "$status" = "401" ] && echo ok || echo FEHLER)" "$status"

# Schreibversuch ohne can_write muss 403 sein (oder klappen, wenn der Key schreiben darf)
status=$(curl -sS -o "$BODY" -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"recipients":["1"],"body":"test"}' "$API/messages/send" || true)
case "$status" in
  403) echo "  ok    Senden gesperrt (Nur-Lese-Key) -> HTTP 403" ;;
  200) echo "  HINWEIS Senden erlaubt: dieser Key hat Schreibzugriff" ;;
  *)   echo "  FEHLER Senden -> HTTP $status  $(head -c 160 "$BODY" | tr -d '\n')" ;;
esac

echo
echo "Fertig. Fehler mit code=TOKEN_INVALID/TOKEN_EXPIRED: Key in Ordnung?"
