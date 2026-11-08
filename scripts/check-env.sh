#!/usr/bin/env bash
# Validate a JoineryFlow production env file before `docker compose up`.
#
# Why this exists (checklist section 3, item 3): a missing field makes
# Settings() raise ValidationError at import. The container crash-loops, and on
# a customer's box that reads as "JoineryFlow is broken" rather than "you forgot
# to set DATABASE_URL". Fail here, with the variable's name, instead.
#
# Usage: scripts/check-env.sh [path/to/.env]   (default: ./.env)
# Exit:  0 = OK, 1 = validation errors, 2 = file/usage problem.
#
# The file is parsed, never sourced: it contains secrets, its values may hold
# shell metacharacters, and sourcing a customer-owned file would execute it.
# Comments must be on their own line (see deploy/.env.prod.example) so that a
# '#' inside a password is left alone.

set -u

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: $0 [path/to/.env]"
  exit 0
fi

ENV_FILE="${1:-./.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  echo "Copy deploy/.env.prod.example, fill it in, chmod 600." >&2
  exit 2
fi
if [ ! -r "$ENV_FILE" ]; then
  echo "ERROR: env file is not readable: $ENV_FILE" >&2
  exit 2
fi

read_var() {
  local key="$1" line
  line=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$ENV_FILE" 2>/dev/null | tail -n 1)
  [ -n "$line" ] || { printf ''; return 0; }
  line=${line#*=}
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  case "$line" in
    \"*\") line=${line#\"}; line=${line%\"} ;;
    \'*\') line=${line#\'}; line=${line%\'} ;;
  esac
  printf '%s' "$line"
}

errors=0
fail() { echo "  ERROR: $1" >&2; errors=$((errors + 1)); }
warn() { echo "  WARN:  $1" >&2; }

echo "Checking $ENV_FILE"

REQUIRED=(
  POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL
  API_URL SESSION_COOKIE_NAME COOKIE_SECURE FILE_STORE_ROOT
  MEILI_MASTER_KEY MEILI_URL MEILI_API_KEY
  JF_VERSION
)

for key in "${REQUIRED[@]}"; do
  value=$(read_var "$key")
  if [ -z "$value" ]; then
    fail "$key is missing or empty"
    continue
  fi
  case "$value" in
    *__SET_ME__*|*CHANGEME*|*changeme*)
      fail "$key still contains a template placeholder"
      ;;
  esac
done

# --- Rules that a simple non-empty check cannot express ---
cookie_secure=$(read_var COOKIE_SECURE)
if [ -n "$cookie_secure" ] && [ "${cookie_secure,,}" != "true" ]; then
  fail "COOKIE_SECURE must be true behind https (checklist section 3, item 4)"
fi

master_key=$(read_var MEILI_MASTER_KEY)
if [ -n "$master_key" ] && [ "${#master_key}" -lt 16 ]; then
  fail "MEILI_MASTER_KEY must be at least 16 bytes (Meilisearch production mode refuses to start)"
fi

api_key=$(read_var MEILI_API_KEY)
if [ -n "$api_key" ] && [ -n "$master_key" ] && [ "$api_key" = "$master_key" ]; then
  warn "MEILI_API_KEY equals MEILI_MASTER_KEY; section 3 item 5 wants them distinct (scoped keys are Phase 1 after D1)"
fi

app_version=$(read_var APP_VERSION)
jf_version=$(read_var JF_VERSION)
if [ -z "$app_version" ]; then
  warn "APP_VERSION is unset; GET /version will report the image's build ARG instead"
elif [ -n "$jf_version" ] && [ "$app_version" != "$jf_version" ]; then
  fail "APP_VERSION and JF_VERSION disagree; support cannot tell which version is running (checklist section 0.1 / 9.2)"
fi

api_url=$(read_var API_URL)
if [ -n "$api_url" ] && [ "$api_url" != "http://api:8000" ]; then
  warn "API_URL is not http://api:8000; Q1 settled on a single hostname with the api inside the compose network"
fi

# File permissions: a secrets file readable by other local users is a finding,
# not a hard failure (and meaningless on Windows hosts).
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*) ;;
  *)
    if command -v stat >/dev/null 2>&1; then
      mode=$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo '')
      if [ -n "$mode" ] && [ "$mode" != "600" ]; then
        warn "env file mode is $mode; chmod 600 $ENV_FILE"
      fi
    fi
    ;;
esac

if [ "$errors" -gt 0 ]; then
  echo "FAILED: $errors problem(s). Fix the variables named above before starting the stack." >&2
  exit 1
fi

echo "OK: all required variables are set and non-empty."
echo "Start with:"
echo "  docker compose --env-file $ENV_FILE -f docker-compose.prod.yml up -d"
exit 0
