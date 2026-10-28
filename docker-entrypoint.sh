#!/bin/sh
# Container entrypoint: prepare the data volume, pin the vault key, drop privileges.
#
# Runs as root only long enough to (a) make the mounted data directory writable by
# the unprivileged app user and (b) create CREDENTIAL_ENCRYPTION_KEY_FILE on first
# start. Then it re-executes the given command as the app user.
set -eu

APP_UID=${APP_UID:-10001}
APP_GID=${APP_GID:-10001}
DATA_DIR=${DATA_DIR:-/app/data}
KEY_FILE=${CREDENTIAL_ENCRYPTION_KEY_FILE:-$DATA_DIR/credential.key}

mkdir -p "$DATA_DIR"

# A bind-mounted ./data belongs to the host user, which is usually not 10001.
if [ "$(id -u)" = "0" ]; then
  chown -R "$APP_UID:$APP_GID" "$DATA_DIR"
fi

# The vault key encrypts the stored EduPage passwords. If it changes, every stored
# credential becomes unreadable, so it must survive container recreation. The app
# reads this file itself, so `docker compose exec` processes see the same key.
if [ -z "${CREDENTIAL_ENCRYPTION_KEY:-}" ] && [ ! -s "$KEY_FILE" ]; then
  mkdir -p "$(dirname "$KEY_FILE")"
  # Create with restrictive permissions before writing the secret into it.
  (umask 077 && python -c 'import secrets; print(secrets.token_hex(32))' > "$KEY_FILE")
  echo "[entrypoint] Neuer Vault-Schluessel erzeugt: $KEY_FILE" >&2
  echo "[entrypoint] Diesen Wert sichern - ohne ihn sind gespeicherte Passwoerter verloren." >&2
fi

if [ -f "$KEY_FILE" ] && [ "$(id -u)" = "0" ]; then
  chown "$APP_UID:$APP_GID" "$KEY_FILE"
fi

if [ "$(id -u)" = "0" ]; then
  exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups "$@"
fi

exec "$@"
