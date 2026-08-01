#!/usr/bin/env bash
set -euo pipefail

load_secret() {
  local variable="$1"
  local path="$2"
  local value
  if [[ ! -r "$path" ]]; then
    echo "Required Keycloak bootstrap secret file is unavailable." >&2
    exit 1
  fi
  value="$(<"$path")"
  if [[ -z "${value//[[:space:]]/}" ]]; then
    echo "Required Keycloak bootstrap secret file is empty." >&2
    exit 1
  fi
  printf -v "$variable" '%s' "$value"
  export "$variable"
  unset value
}

load_secret DA_KEYCLOAK_BOOTSTRAP_USERNAME /run/secrets/keycloak-admin-username
load_secret DA_KEYCLOAK_BOOTSTRAP_PASSWORD /run/secrets/keycloak-admin-password
load_secret KC_DB_PASSWORD /run/secrets/keycloak-db-password

# Keycloak 26.7 emits the temporary administrator username in this one event.
# Preserve all other output and retain the event itself with only its payload redacted.
/opt/keycloak/bin/kc.sh "$@" 2>&1 | while IFS= read -r line; do
  if [[ "$line" =~ ^.*INFO[[:space:]]+\[org\.keycloak\.services\][[:space:]]+\(main\)[[:space:]]+KC-SERVICES0077:[[:space:]] ]]; then
    prefix="${line%%KC-SERVICES0077:*}"
    printf '%sKC-SERVICES0077: [REDACTED_BOOTSTRAP_ADMIN]\n' "$prefix"
  else
    printf '%s\n' "$line"
  fi
done
