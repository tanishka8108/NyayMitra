#!/usr/bin/env bash
# ============================================================================
# NyayMitra — stop the services started by scripts/start_all.sh
#
#   ./scripts/stop_all.sh              stop everything this repo started
#   ./scripts/stop_all.sh --lawyer     stop only the Lawyer API    :8000
#   ./scripts/stop_all.sh --nlp        stop only the NLP service   :8001
#   ./scripts/stop_all.sh --model      stop only the Model API     :8002
#   ./scripts/stop_all.sh --web        stop only the frontend      :5173
#
# Only processes whose pid file was written by start_all.sh are signalled,
# so another team member's Vite or uvicorn is never killed by accident.
# PostgreSQL is left running — stop it yourself only if you mean to:
#     sudo systemctl stop postgresql
# ============================================================================
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$HOME/.nyaymitra/pids"
LOG_DIR="$HOME/.nyaymitra/logs"

TARGETS=(lawyer nlp model web)

# Accept --<service> for any of the four. An unrecognised flag must
# refuse and stop nothing: silently falling back to "stop everything"
# turns a typo into an outage.
if [ "$#" -gt 0 ]; then
  case "$1" in
    --lawyer|--nlp|--model|--web)
      TARGETS=("${1#--}")
      ;;
    --help|-h)
      sed -n '2,12p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      printf 'Unknown target: %s\n' "$1" >&2
      printf 'Use one of: --lawyer --nlp --model --web\n' >&2
      printf 'Nothing was stopped.\n' >&2
      exit 2
      ;;
  esac
fi

stop_one() {
  local name="$1" pid
  if [ ! -f "$PID_DIR/$name.pid" ]; then
    printf '  %-8s not running (no pid file)\n' "$name"; return
  fi
  pid="$(cat "$PID_DIR/$name.pid")"
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_DIR/$name.pid"
    printf '  %-8s already stopped (stale pid removed)\n' "$name"; return
  fi
  # Guard against a recycled pid: only signal it if the process still
  # looks like one of the services this project starts. A pid handed
  # to somebody else's process must never be killed.
  if [ -r "/proc/$pid/cmdline" ]; then
    cmd="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
    case "$cmd" in
      *uvicorn*|*vite*|*npm*|*node*) ;;
      *)
        printf '  %-8s pid %s is no longer a NyayMitra service (left alone)\n' "$name" "$pid"
        rm -f "$PID_DIR/$name.pid"
        return
        ;;
    esac
  fi
  kill "$pid" 2>/dev/null
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null
    printf '  %-8s stopped (force, pid %s)\n' "$name" "$pid"
  else
    printf '  %-8s stopped (pid %s)\n' "$name" "$pid"
  fi
  rm -f "$PID_DIR/$name.pid"
}

echo "Stopping:"
for n in "${TARGETS[@]}"; do stop_one "$n"; done

echo
echo "Logs kept in $LOG_DIR"
echo "PostgreSQL is untouched. Anything this script did not start keeps running."
