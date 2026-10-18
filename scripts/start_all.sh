#!/usr/bin/env bash
# ============================================================================
# NyayMitra — start every core service (safe to re-run; never starts a
# duplicate on a port that is already serving).
#
#   ./scripts/start_all.sh          start whatever is not up yet
#   ./scripts/start_all.sh --force  restart anything already running
#
# Core services   Lawyer API :8000 · NLP :8001 · Model API :8002 · Web :5173
# Optional        PostgreSQL :5432  (only the lawyer directory needs it;
#                 auth, chat and My Cases run on SQLite without it)
#
# Logs and pid files live OUTSIDE the repository, in ~/.nyaymitra/, so the
# working tree gains nothing but the scripts themselves. No credential is
# printed anywhere.
# ============================================================================
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$HOME/.nyaymitra"
LOG_DIR="$RUN_DIR/logs"
PID_DIR="$RUN_DIR/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

# Node lives under nvm, which a non-interactive shell does not load.
export PATH="/home/tanishka/.nvm/versions/node/v22.23.3/bin:$PATH"

LAWYER_PORT=8000
NLP_PORT=8001
MODEL_PORT=8002
WEB_PORT=5173

in_use() { ss -ltn 2>/dev/null | grep -qE ":$1\b"; }

# `alive <name>` — the pid file's process is still running.
alive()  { [ -f "$PID_DIR/$1.pid" ] && kill -0 "$(cat "$PID_DIR/$1.pid")" 2>/dev/null; }

stop_one() { # name
  if alive "$1"; then
    # Same identity guard as stop_all.sh: a recycled pid must never be
    # signalled just because it sits in our file.
    local pid cmd
    pid="$(cat "$PID_DIR/$1.pid")"
    if [ -r "/proc/$pid/cmdline" ]; then
      cmd="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
      case "$cmd" in
        *uvicorn*|*vite*|*npm*|*node*) ;;
        *) printf '  %-14s pid %s is no longer a NyayMitra service (left alone)\n' "$1" "$pid"
           rm -f "$PID_DIR/$1.pid"; return ;;
      esac
    fi
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 20); do alive "$1" || break; sleep 0.5; done
    alive "$1" && kill -9 "$pid" 2>/dev/null
    rm -f "$PID_DIR/$1.pid"
  fi
}

# Names this invocation actually launched. A service that was already
# serving when the script ran belongs to somebody else (or to an earlier
# run) and its pid is deliberately NOT recorded, so stop_all.sh will not
# signal a process this run never started.
STARTED=" "

start_one() { # name port url workdir -- command...
  local name="$1" port="$2" url="$3" workdir="$4"; shift 4
  if in_use "$port"; then
    if [ "$FORCE" = 1 ]; then
      printf '  %-14s port %s busy -> restarting\n' "$name" "$port"
      stop_one "$name"; sleep 1
      in_use "$port" && { printf '  %-14s STOPPED (port %s still held by another process)\n' "$name" "$port"; return 1; }
    else
      printf '  %-14s already serving on :%s (left alone)\n' "$name" "$port"
      return 0
    fi
  fi
  # `setsid` puts the service in a NEW session, detached from this
  # script. Without it the service dies the moment the launching
  # shell exits — which is exactly what happens when the script is
  # run as `wsl.exe -- scripts/start_all.sh`, because wsl.exe tears
  # down its own session tree on exit. stdin comes from /dev/null so
  # nothing ever waits for input.
  setsid bash -c 'cd "$1" || exit 1; shift; exec "$@"' _ "$workdir" "$@" \
    >"$LOG_DIR/$name.log" 2>&1 </dev/null &
  STARTED="$STARTED$name "
  printf '  %-14s starting -> log %s\n' "$name" "$LOG_DIR/$name.log"
}

# The listener's real pid, read back off the port. `setsid` may fork, so
# $? of the launch above is not the service itself — this is.
listener_pid() {
  ss -ltnp 2>/dev/null | grep -E ":$1\b" \
    | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2
}

record_pids() { # name port
  local pid=""
  # Only a service this invocation launched gets a pid file; one that was
  # already up is left for whoever owns it.
  case $STARTED in
    *" $1 "*) ;;
    *) printf '  %-14s not started by this run (no pid recorded)\n' "$1"; return ;;
  esac
  for _ in $(seq 1 40); do
    pid="$(listener_pid "$2")"
    [ -n "$pid" ] && break
    sleep 1
  done
  if [ -n "$pid" ]; then
    echo "$pid" >"$PID_DIR/$1.pid"
    printf '  %-14s pid %s recorded\n' "$1" "$pid"
  else
    printf '  %-14s no listener found on :%s (stop it by hand)\n' "$1" "$2"
  fi
}

echo "== 1. PostgreSQL (optional; only the lawyer directory needs it) =="
if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  echo "   UP on 127.0.0.1:5432"
else
  echo "   DOWN — auth / chat / My Cases still work (SQLite);"
  echo "         /api/lawyers and /api/practice-areas will answer 500."
fi

echo
echo "== 2. Backend services =="
start_one lawyer "$LAWYER_PORT" "http://127.0.0.1:$LAWYER_PORT" \
  "$REPO/NyayMitra-feature-lawyer-api" \
  .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "$LAWYER_PORT"

start_one nlp "$NLP_PORT" "http://127.0.0.1:$NLP_PORT" \
  "$REPO/NyayMitra-feature-nlp-translation" \
  env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m uvicorn translate_service:app --host 127.0.0.1 --port "$NLP_PORT"

if [ -x "$REPO/.venv/bin/python" ]; then
  start_one model "$MODEL_PORT" "http://127.0.0.1:$MODEL_PORT" \
    "$REPO" \
    env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    PYTHONPATH="$REPO/src" \
    .venv/bin/python -m uvicorn api:app --app-dir src \
    --host 127.0.0.1 --port "$MODEL_PORT"
else
  printf '  %-14s SKIPPED — %s/.venv not built yet (see scripts/README)\n' "model" "$REPO"
fi

echo
echo "== 3. Frontend =="
start_one web "$WEB_PORT" "http://localhost:$WEB_PORT" \
  "$REPO/frontend" npm run dev -- --port "$WEB_PORT" --strictPort

echo
echo "== 4. Waiting for each service to answer =="
wait_for() { # name url path
  local name="$1" url="$2" path="$3" code=""
  for _ in $(seq 1 40); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url$path" 2>/dev/null)
    [ "$code" = "200" ] && { printf '  %-14s 200 OK\n' "$name"; return 0; }
    sleep 1
  done
  printf '  %-14s no 200 yet (last=%s) — check %s\n' "$name" "${code:-none}" "$LOG_DIR/$name.log"
  return 1
}
wait_for lawyer "http://127.0.0.1:$LAWYER_PORT" "/"
wait_for nlp    "http://127.0.0.1:$NLP_PORT"    "/health"
[ -x "$REPO/.venv/bin/python" ] && wait_for model "http://127.0.0.1:$MODEL_PORT" "/health"
wait_for web    "http://localhost:$WEB_PORT"    "/"

echo
echo "== 5. Recording pids (what stop_all.sh will signal) =="
record_pids lawyer "$LAWYER_PORT"
record_pids nlp    "$NLP_PORT"
[ -x "$REPO/.venv/bin/python" ] && record_pids model "$MODEL_PORT"
record_pids web    "$WEB_PORT"

echo
exec "$REPO/scripts/health.sh"
