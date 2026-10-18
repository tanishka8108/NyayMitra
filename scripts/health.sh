#!/usr/bin/env bash
# ============================================================================
# NyayMitra — health check (read-only; prints nothing secret)
#   ./scripts/health.sh
# Checks PostgreSQL plus the three backend services and the Vite dev server,
# then prints each service's real URL and its actual HTTP status.
# ============================================================================
set -u

LAWYER_URL="${VITE_API_BASE_URL:-http://127.0.0.1:8000}"
NLP_URL="${VITE_TRANSLATION_API_URL:-http://127.0.0.1:8001}"
MODEL_URL="${VITE_MODEL_API_URL:-http://127.0.0.1:8002}"
WEB_URL="http://localhost:5173"

ok=0; bad=0

row() { # $1 label $2 state $3 url
  printf '  %-22s %-9s %s\n' "$1" "$2" "$3"
}

echo "== PostgreSQL =="
if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  row "postgres 5432" "UP" "127.0.0.1:5432"
else
  row "postgres 5432" "DOWN" "127.0.0.1:5432"; bad=$((bad+1))
fi

echo
echo "== Services =="
check() { # $1 label $2 url $3 path
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$2$3" 2>/dev/null)
  if [ "$code" = "200" ]; then
    row "$1" "UP" "$2   (GET $3 -> 200)"; ok=$((ok+1))
  else
    row "$1" "DOWN" "$2   (GET $3 -> ${code:-no response})"; bad=$((bad+1))
  fi
}

check "Lawyer API 8000"  "$LAWYER_URL" "/"
check "NLP service 8001" "$NLP_URL"    "/health"
check "Model API 8002"   "$MODEL_URL"  "/health"
check "Frontend 5173"    "$WEB_URL"    "/"

echo
echo "== Lawyer directory (needs PostgreSQL schema) =="
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "$LAWYER_URL/api/lawyers" 2>/dev/null)
case "$code" in
  200) echo "  /api/lawyers -> 200  (directory serving real rows)";;
  500) echo "  /api/lawyers -> 500  (PostgreSQL role/schema not ready)"; bad=$((bad+1));;
  *)   echo "  /api/lawyers -> ${code:-no response}"; bad=$((bad+1));;
esac

echo
echo "up=$ok  failing=$bad"
[ "$bad" -eq 0 ] && exit 0 || exit 1
