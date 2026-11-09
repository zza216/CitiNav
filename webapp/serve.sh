#!/usr/bin/env bash
# Serve the CitiNav web simulator on the LAN so you can open it from your phone.
#
#   ./serve.sh [port]        # default port 8000
#
# Web Bluetooth only runs in a SECURE context. http://localhost:PORT works on
# the Mac, but on the phone you must add the LAN origin to Chrome's allowlist
# (option A) or use an https tunnel (option B). This script prints both.

set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8000}"
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)"

cat <<EOF
CitiNav web simulator
=====================
  On this Mac (secure, works immediately):
      http://localhost:$PORT

  On your phone (same Wi-Fi):
      http://$IP:$PORT

Web Bluetooth needs a secure context. On the phone use ONE of:

  A) Allow this origin in Chrome (no internet, easiest)
     1. open   chrome://flags/#unsafely-treat-insecure-origin-as-secure
     2. add     http://$IP:$PORT
     3. set it to Enabled, Relaunch Chrome, then open the URL above
     (Chrome will warn the origin is treated as secure — that's expected.)

  B) https tunnel (robust; needs a tool)
     cloudflared:  brew install cloudflared
                   cloudflared tunnel --url http://localhost:$PORT
     ngrok:        npx ngrok http $PORT
     then open the printed https:// URL on the phone.

Keep this terminal running. Mac IP can change when you rejoin Wi-Fi.
EOF

exec python3 -m http.server "$PORT" --bind 0.0.0.0
