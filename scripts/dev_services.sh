#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUNTIME_DIR="$ROOT_DIR/runtime/dev-services"
LOG_DIR="$ROOT_DIR/runtime/logs"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5180}"
BLENDER_PORT="${BLENDER_PORT:-9876}"
BLENDER_LIVE_TIMEOUT_SECONDS="${BLENDER_LIVE_TIMEOUT_SECONDS:-900}"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend-dev.log"
FRONTEND_LOG="$LOG_DIR/frontend-dev.log"

BACKEND_PYTHON="${BACKEND_PYTHON:-$BACKEND_DIR/.venv/bin/python}"
NPM_BIN="${NPM_BIN:-$(command -v npm || true)}"
LAUNCHER_PYTHON="${LAUNCHER_PYTHON:-$(command -v python3 || true)}"

usage() {
  cat <<EOF
Usage: scripts/dev_services.sh <start|stop|restart|status|logs>

Commands:
  start      Start live backend and frontend
  stop       Stop backend/frontend using PID files and dev ports
  restart    Stop, then start both services
  status     Show process and endpoint status
  logs       Tail backend and frontend logs

Defaults:
  backend:  http://127.0.0.1:${BACKEND_PORT}
  frontend: http://127.0.0.1:${FRONTEND_PORT}
  blender:  live render on port ${BLENDER_PORT}

Override examples:
  BACKEND_PORT=8010 FRONTEND_PORT=5181 scripts/dev_services.sh restart
  BLENDER_PORT=9877 scripts/dev_services.sh start
EOF
}

ensure_dirs() {
  mkdir -p "$RUNTIME_DIR" "$LOG_DIR"
}

pid_is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid_file() {
  local file="$1"
  [[ -f "$file" ]] && tr -d '[:space:]' < "$file" || true
}

port_pids() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

kill_tree() {
  local pid="${1:-}"
  [[ -n "$pid" ]] || return 0
  pid_is_running "$pid" || return 0

  local children child
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  for child in $children; do
    kill_tree "$child"
  done
  kill -TERM "$pid" 2>/dev/null || true
}

wait_for_pids_to_exit() {
  local pids=("$@")
  local alive pid

  for _ in {1..40}; do
    alive=0
    for pid in "${pids[@]}"; do
      if pid_is_running "$pid"; then
        alive=1
      fi
    done
    [[ "$alive" -eq 0 ]] && return 0
    sleep 0.25
  done

  for pid in "${pids[@]}"; do
    kill -KILL "$pid" 2>/dev/null || true
  done
}

stop_pid_file() {
  local name="$1"
  local file="$2"
  local pid
  pid="$(read_pid_file "$file")"

  if pid_is_running "$pid"; then
    echo "Stopping $name pid $pid"
    kill_tree "$pid"
    wait_for_pids_to_exit "$pid"
  fi
  rm -f "$file"
}

stop_port() {
  local name="$1"
  local port="$2"
  local pids pid ppid parent_cmd
  pids="$(port_pids "$port")"
  [[ -n "$pids" ]] || return 0

  for pid in $pids; do
    echo "Stopping $name listener on port $port pid $pid"

    ppid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true)"
    parent_cmd="$(ps -o command= -p "$ppid" 2>/dev/null || true)"

    if [[ "$parent_cmd" == *"npm run dev"* || "$parent_cmd" == *"app.main"* ]]; then
      kill_tree "$ppid"
    fi
    kill_tree "$pid"
  done

  # Give reloaders/watchers a moment, then force anything still bound to the port.
  for _ in {1..40}; do
    [[ -z "$(port_pids "$port")" ]] && return 0
    sleep 0.25
  done
  for pid in $(port_pids "$port"); do
    kill -KILL "$pid" 2>/dev/null || true
  done
}

stop_services() {
  ensure_dirs
  stop_pid_file "backend" "$BACKEND_PID_FILE"
  stop_pid_file "frontend" "$FRONTEND_PID_FILE"
  stop_port "backend" "$BACKEND_PORT"
  stop_port "frontend" "$FRONTEND_PORT"
  echo "Stopped dev services."
}

check_start_requirements() {
  if [[ ! -x "$BACKEND_PYTHON" ]]; then
    echo "Missing backend Python: $BACKEND_PYTHON"
    echo "Run: make backend-install"
    exit 1
  fi
  if [[ -z "$NPM_BIN" || ! -x "$NPM_BIN" ]]; then
    echo "Missing npm. Install Node/npm, then run: make frontend-install"
    exit 1
  fi
  if [[ -z "$LAUNCHER_PYTHON" || ! -x "$LAUNCHER_PYTHON" ]]; then
    echo "Missing python3, needed only to detach both services cleanly."
    exit 1
  fi
  if [[ -n "$(port_pids "$BACKEND_PORT")" || -n "$(port_pids "$FRONTEND_PORT")" ]]; then
    echo "One of the dev ports is already in use. Run restart instead:"
    echo "  scripts/dev_services.sh restart"
    status_services
    exit 1
  fi
}

start_services() {
  ensure_dirs
  check_start_requirements
  touch "$BACKEND_LOG" "$FRONTEND_LOG"

  ROOT_DIR="$ROOT_DIR" \
  BACKEND_DIR="$BACKEND_DIR" \
  FRONTEND_DIR="$FRONTEND_DIR" \
  BACKEND_PYTHON="$BACKEND_PYTHON" \
  NPM_BIN="$NPM_BIN" \
  BACKEND_PID_FILE="$BACKEND_PID_FILE" \
  FRONTEND_PID_FILE="$FRONTEND_PID_FILE" \
  BACKEND_LOG="$BACKEND_LOG" \
  FRONTEND_LOG="$FRONTEND_LOG" \
  BACKEND_PORT="$BACKEND_PORT" \
  FRONTEND_PORT="$FRONTEND_PORT" \
  BLENDER_PORT="$BLENDER_PORT" \
  BLENDER_LIVE_TIMEOUT_SECONDS="$BLENDER_LIVE_TIMEOUT_SECONDS" \
  "$LAUNCHER_PYTHON" <<'PY'
import os
import subprocess
from pathlib import Path

backend_env = os.environ.copy()
backend_env.update({
    "BLENDER_PORT": os.environ["BLENDER_PORT"],
    "BLENDER_LIVE_RENDER": "1",
    "BLENDER_LIVE_TIMEOUT_SECONDS": os.environ["BLENDER_LIVE_TIMEOUT_SECONDS"],
})

frontend_env = os.environ.copy()
frontend_env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + frontend_env.get("PATH", "")

backend_log = open(os.environ["BACKEND_LOG"], "ab", buffering=0)
frontend_log = open(os.environ["FRONTEND_LOG"], "ab", buffering=0)

backend = subprocess.Popen(
    [os.environ["BACKEND_PYTHON"], "-m", "app.main"],
    cwd=os.environ["BACKEND_DIR"],
    stdin=subprocess.DEVNULL,
    stdout=backend_log,
    stderr=subprocess.STDOUT,
    env=backend_env,
    start_new_session=True,
)
frontend = subprocess.Popen(
    [
        os.environ["NPM_BIN"],
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        os.environ["FRONTEND_PORT"],
    ],
    cwd=os.environ["FRONTEND_DIR"],
    stdin=subprocess.DEVNULL,
    stdout=frontend_log,
    stderr=subprocess.STDOUT,
    env=frontend_env,
    start_new_session=True,
)

Path(os.environ["BACKEND_PID_FILE"]).write_text(str(backend.pid) + "\n")
Path(os.environ["FRONTEND_PID_FILE"]).write_text(str(frontend.pid) + "\n")
print(f"Started backend pid {backend.pid}")
print(f"Started frontend pid {frontend.pid}")
PY

  wait_for_url "http://127.0.0.1:${BACKEND_PORT}/api/parser/health" "backend"
  wait_for_url "http://127.0.0.1:${FRONTEND_PORT}" "frontend"
  echo "Backend:  http://127.0.0.1:${BACKEND_PORT}"
  echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
  echo "Logs:     $BACKEND_LOG"
  echo "          $FRONTEND_LOG"
}

wait_for_url() {
  local url="$1"
  local name="$2"
  command -v curl >/dev/null 2>&1 || return 0

  for _ in {1..60}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready."
      return 0
    fi
    sleep 0.5
  done

  echo "$name did not answer yet. Check logs:"
  echo "  $BACKEND_LOG"
  echo "  $FRONTEND_LOG"
  return 1
}

service_line() {
  local name="$1"
  local file="$2"
  local port="$3"
  local pid pids
  pid="$(read_pid_file "$file")"
  pids="$(port_pids "$port" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"

  if pid_is_running "$pid"; then
    echo "$name: pid $pid, port $port listeners: ${pids:-none}"
  elif [[ -n "$pids" ]]; then
    echo "$name: no PID file, but port $port listeners: $pids"
  else
    echo "$name: stopped"
  fi
}

status_services() {
  ensure_dirs
  service_line "backend" "$BACKEND_PID_FILE" "$BACKEND_PORT"
  service_line "frontend" "$FRONTEND_PID_FILE" "$FRONTEND_PORT"

  if command -v curl >/dev/null 2>&1; then
    if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/parser/health" >/dev/null 2>&1; then
      echo "backend health: ok"
    else
      echo "backend health: not responding"
    fi
    if curl -fsSI "http://127.0.0.1:${FRONTEND_PORT}" >/dev/null 2>&1; then
      echo "frontend health: ok"
    else
      echo "frontend health: not responding"
    fi
  fi
}

tail_logs() {
  ensure_dirs
  touch "$BACKEND_LOG" "$FRONTEND_LOG"
  tail -n 80 -f "$BACKEND_LOG" "$FRONTEND_LOG"
}

case "${1:-}" in
  start)
    start_services
    ;;
  stop)
    stop_services
    ;;
  restart)
    stop_services
    start_services
    ;;
  status)
    status_services
    ;;
  logs)
    tail_logs
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1"
    usage
    exit 2
    ;;
esac
