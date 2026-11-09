#!/usr/bin/env bash
# CitiNav deploy - copy firmware to the board and (re)start it.
#
# Usage:
#   ./deploy.sh                              # auto-detect the USB serial port
#   ./deploy.sh /dev/cu.usbmodem101          # explicit port
#   PORT=/dev/cu.usbmodem101 ./deploy.sh     # via env var
#
# Copies main.py + citinav_landscape.py (+ citinav.py) to the board, then
# soft-resets so the landscape (v2) UI boots immediately.
#
# Gotcha this script hides: mpremote needs '+' BETWEEN chained commands.
# Without it, 'cp' treats the next word (e.g. 'reset') as the copy destination.

set -euo pipefail

MPREMOTE="$HOME/.esptool-venv/bin/mpremote"
[ -x "$MPREMOTE" ] || MPREMOTE="mpremote"

cd "$(dirname "$0")"

# ---- pick the port ----
PORT="${1:-${PORT:-}}"
if [ -z "$PORT" ]; then
    PORT="$("$MPREMOTE" devs 2>/dev/null | awk '/usbmodem/ {print $1; exit}')"
fi
if [ -z "$PORT" ]; then
    echo "! no /dev/cu.usbmodem* port found."
    echo "  Plug the board in with a data-capable USB-C cable, then retry."
    echo "  ports currently seen:"
    "$MPREMOTE" devs 2>/dev/null | sed 's/^/    /'
    exit 1
fi
echo "-> port: $PORT"

FILES=(main.py citinav_landscape.py citinav.py)

# ---- build the chained command: connect PORT cp f :f + cp f :f + ... + reset ----
ARGS=(connect "$PORT")
for f in "${FILES[@]}"; do
    [ -f "$f" ] || { echo "! missing local file: $f"; exit 1; }
    ARGS+=(cp "$f" ":$f" +)
done
ARGS+=(reset)

echo "-> deploying: ${FILES[*]}"
"$MPREMOTE" "${ARGS[@]}"

echo "-> done. Board should now be running the landscape (v2) UI."
echo "   (if it just sits at the REPL instead, press Ctrl-D or the RST button)"
