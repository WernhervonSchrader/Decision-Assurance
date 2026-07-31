#!/usr/bin/env bash
set -euo pipefail

load_secret() {
  local variable="$1"
  local path="$2"
  local value
  if [[ ! -r "$path" ]]; then
    echo "Required Keycloak secret file is unavailable." >&2
    exit 1
  fi
  value="$(<"$path")"
  if [[ -z "${value//[[:space:]]/}" ]]; then
    echo "Required Keycloak secret file is empty." >&2
    exit 1
  fi
  printf -v "$variable" '%s' "$value"
  export "$variable"
  unset value
}

load_secret KC_BOOTSTRAP_ADMIN_USERNAME /run/secrets/keycloak-admin-username
load_secret KC_BOOTSTRAP_ADMIN_PASSWORD /run/secrets/keycloak-admin-password
load_secret KC_DB_PASSWORD /run/secrets/keycloak-db-password

exec /opt/keycloak/bin/kc.sh "$@"
