#!/usr/bin/env bash
#
# run.sh — CitiNav local web server + Cloudflare quick tunnel.
#
#   ./run.sh start     serve webapp/ on :PORT and open a trycloudflare.com tunnel
#   ./run.sh stop      stop the server and the tunnel
#   ./run.sh status    show what is running and the tunnel URL
#
# It serves the webapp/ next to this script, so run it from the checkout you want
# to test (e.g. this PR worktree). Both processes are detached; their logs live
# in the state dir printed by `status`.
#
# Env overrides:
#   PORT=8000            port to serve on
#   HOST=0.0.0.0         bind address (0.0.0.0 also exposes it on the LAN)
#   CLOUDFLARED=cloudflared
#
# No restart command — use `stop` then `start`.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
CLOUDFLARED="${CLOUDFLARED:-cloudflared}"
WEBROOT="$ROOT/webapp"

# Keep state per-checkout so main and a PR worktree can run side by side.
STATE_DIR="${TMPDIR:-/tmp}/citinav-run-$(printf '%s' "$ROOT" | cksum | awk '{print $1}')"
SRV_PID="$STATE_DIR/server.pid"
TUN_PID="$STATE_DIR/tunnel.pid"
SRV_LOG="$STATE_DIR/server.log"
TUN_LOG="$STATE_DIR/tunnel.log"

say() { printf '%s\n' "$*"; }
die() { printf '! %s\n' "$*" >&2; exit 1; }

pid_of() { [ -f "$1" ] && cat "$1" 2>/dev/null; }

is_running() {
  local pid
  pid="$(pid_of "$1" || true)"
  [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null
}

port_busy() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; }

lan_ip() {
  ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<mac-ip>"
}

tunnel_url() {
  [ -f "$TUN_LOG" ] || return 0
  grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUN_LOG" 2>/dev/null | head -1 || true
}

wait_http() {
  local i
  for i in $(seq 1 40); do
    if curl -sf -o /dev/null "http://localhost:$PORT/"; then return 0; fi
    sleep 0.25
  done
  return 1
}

wait_url() {
  local i
  for i in $(seq 1 60); do
    if [ -n "$(tunnel_url)" ]; then return 0; fi
    is_running "$TUN_PID" || return 1     # tunnel died early?
    sleep 0.5
  done
  return 1
}

public_ok() {
  local url host ip code
  url="$(tunnel_url)"
  [ -n "$url" ] || return 1
  host="${url#https://}"
  # System resolver first; some networks (locked-down/campus DNS) don't resolve
  # fresh trycloudflare names promptly, so fall back to a public resolver.
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "$url/" 2>/dev/null || true)"
  if [ "$code" != "200" ] && command -v dig >/dev/null 2>&1; then
    ip="$(dig +short @1.1.1.1 "$host" 2>/dev/null | head -1 || true)"
    if [ -n "$ip" ]; then
      code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 \
        --resolve "$host:443:$ip" "$url/" 2>/dev/null || true)"
    fi
  fi
  [ "$code" = "200" ]
}

wait_public() {
  local i
  for i in $(seq 1 45); do
    if public_ok; then return 0; fi
    is_running "$TUN_PID" || return 1
    sleep 1
  done
  return 1
}

stop_one() {
  local pf="$1" name="$2" pid i
  if is_running "$pf"; then
    pid="$(pid_of "$pf")"
    kill "$pid" 2>/dev/null || true
    for i in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    kill -9 "$pid" 2>/dev/null || true
    say "$name: stopped (pid $pid)"
  else
    say "$name: not running"
  fi
  rm -f "$pf"
}

start_server() {
  if is_running "$SRV_PID"; then
    say "server: already running (pid $(pid_of "$SRV_PID"))"
    return 0
  fi
  [ -d "$WEBROOT" ] || die "no webapp/ directory in $ROOT"
  if port_busy; then
    die "port $PORT is already in use — stop that first, or run with PORT=<other>"
  fi
  mkdir -p "$STATE_DIR"
  : > "$SRV_LOG"
  nohup python3 -m http.server "$PORT" --bind "$HOST" --directory "$WEBROOT" >"$SRV_LOG" 2>&1 &
  echo $! > "$SRV_PID"
  if wait_http; then
    say "server: started (pid $(pid_of "$SRV_PID"))  http://localhost:$PORT  (LAN http://$(lan_ip):$PORT)"
  else
    say "server: failed to come up — see $SRV_LOG"
    stop_one "$SRV_PID" "server"
    exit 1
  fi
}

start_tunnel() {
  if is_running "$TUN_PID"; then
    say "tunnel: already running (pid $(pid_of "$TUN_PID"))  $(tunnel_url)"
    return 0
  fi
  command -v "$CLOUDFLARED" >/dev/null 2>&1 || \
    die "cloudflared not found (brew install cloudflared, or set CLOUDFLARED=/path/to/it)"
  mkdir -p "$STATE_DIR"
  : > "$TUN_LOG"
  nohup "$CLOUDFLARED" tunnel --url "http://localhost:$PORT" >"$TUN_LOG" 2>&1 &
  echo $! > "$TUN_PID"
  if wait_url; then
    local url
    url="$(tunnel_url)"
    say "tunnel: created (pid $(pid_of "$TUN_PID"))  $url"
    if wait_public; then
      say "tunnel: reachable ✓"
      say "phone : open $url"
    else
      say "tunnel: URL is live but not reachable yet (DNS can lag) — try it again in a few seconds"
    fi
  else
    say "tunnel: no URL yet — check $TUN_LOG"
  fi
}

cmd_start() {
  mkdir -p "$STATE_DIR"
  start_server
  start_tunnel
  say ""
  cmd_status
}

cmd_stop() {
  stop_one "$TUN_PID" "tunnel"
  stop_one "$SRV_PID" "server"
  if port_busy; then
    say "! port $PORT is still busy — something else is listening:"
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN | sed 's/^/    /'
  fi
}

cmd_status() {
  local url
  say "CitiNav run — $ROOT"
  say "state : $STATE_DIR"
  say "port  : $PORT"
  if is_running "$SRV_PID"; then
    say "server: running (pid $(pid_of "$SRV_PID"))  http://localhost:$PORT  (LAN http://$(lan_ip):$PORT)"
  else
    say "server: stopped"
  fi
  if is_running "$TUN_PID"; then
    url="$(tunnel_url)"
    say "tunnel: running (pid $(pid_of "$TUN_PID"))  ${url:-starting…}"
    if [ -n "$url" ]; then say "phone : open $url"; fi
  else
    say "tunnel: stopped"
  fi
}

usage() {
  cat <<EOF
usage: $(basename "$0") {start|stop|status}

  start   serve webapp/ on :$PORT and open a Cloudflare quick tunnel
  stop    stop the server and the tunnel
  status  show what is running and the tunnel URL

env: PORT (default 8000) · HOST (default 0.0.0.0) · CLOUDFLARED (default cloudflared)
EOF
}

case "${1:-}" in
  start)              cmd_start ;;
  stop)               cmd_stop ;;
  status)             cmd_status ;;
  ""|-h|--help|help)  usage ;;
  *)                  usage >&2; exit 2 ;;
esac
