# CitiNav — Testing Guide

*How to test the device, the BLE link, and the web apps — from a 10-second
smoke test to a full navigation run.*

---

## Before you start

- [ ] Board powered, LCD showing **`CitiNav`** in yellow with the **green bicycle**
      (if it shows arrows, send `X`; if it's blank, power-cycle).
- [ ] Mac venv present: `~/.esptool-venv/bin/python` (has `bleak`).
- [ ] Board on USB if you need to re-flash (`./deploy.sh`).
- [ ] Nothing else connected to the device — a peripheral **can't advertise while
      connected**, so close the phone app / any other client first.

---

## Test 1 — Is the board alive? (BLE scan)

```bash
~/.esptool-venv/bin/python - <<'PY'
import asyncio
from bleak import BleakScanner
async def main():
    d = await BleakScanner.find_device_by_name("CitiNav", timeout=15)
    print("CitiNav:", d.address if d else "NOT advertising")
asyncio.run(main())
PY
```

**Pass:** prints an address (e.g. `527EF0E7-…`).
**Fail:** "NOT advertising" → board not running / already connected / ghost
connection → hard-reset or power-cycle, close any connected client.

---

## Test 2 — Send commands from the Mac (terminal sender)

The fastest end-to-end test. `citinav_send.py` scans, connects, writes, and logs
the `ack`.

```bash
cd /Users/zakaria/Documents/pi/ESP32/LCD147

./citinav_send.py "L:Broadway:45"     # left + banner + 45 m
./citinav_send.py R LB S U A X        # several in a row (one-shot)
./citinav_send.py                     # interactive; type commands, Q to quit
```

Each send should print `sent <cmd>` and an `ack:<cmd>` line:

```
scanning for CitiNav ...
connected: 527EF0E7-3635-D46B-7243-39C783D074E3
   sent L:Broadway:45
   ack: ack:L
```

**Expected LCD for each command:**

| Send | Device shows |
|---|---|
| `L` | 3-arrow row, **left** green + boxed, label **TURN LEFT** |
| `R` | right green + boxed, **TURN RIGHT** |
| `S` | straight green + boxed, **GO STRAIGHT** |
| `LB` / `RB` / `SB` | same but the active arrow **blinks** |
| `U` | **U-turn** glyph, label **U-TURN** |
| `A` | **ARRIVED** screen |
| `X` | **`CitiNav` + bicycle** boot screen |
| `L:Broadway` | left arrow + banner **Broadway** |
| `L:Broadway:45` | … + label **TURN LEFT  45m** |

**Pass:** the screen matches the table **and** `ack:<cmd>` arrives for every
command. **Fail:** no ack → old firmware (re-flash); wrong screen → parsing bug.

> Gotcha: after `mpremote`/`deploy.sh`, the board may sit at the REPL — send
> `Ctrl-D` (or press RST) so it runs `main.py`.

---

## Test 3 — Web app on the Mac (localhost)

Chrome on the Mac supports Web Bluetooth, so you can test without a phone.

```bash
./webapp/serve.sh
# open http://localhost:8000 in Chrome
```

- **Control tab** → **Connect device** → pick `CitiNav` → tap the arrows.
  The device should react and the Log shows `→ L:…` and `← ack:L`.
- **Route tab** → search a place, drag the pin, pick a mode → **Start in Google
  Maps** opens Maps (and sends `S:<destination>` to the device).

**Pass:** connection persists, commands + acks appear, map/search/reverse work.
**Desk trick:** Chrome DevTools → **Sensors** → *Location* override to feed fake
coordinates (useful for the Nav test, below).

---

## Test 4 — Web app on the phone (via Cloudflare Tunnel)

See [`SETUP.md`](SETUP.md) for the full setup. Short version:

```bash
./webapp/serve.sh                                 # terminal 1
cloudflared tunnel --url http://localhost:8000    # terminal 2 → https URL
```

Open the **https://…trycloudflare.com** URL in the phone's Chrome →
**Connect device** → `CitiNav`. (Optional: **Add to Home screen** for the PWA.)

**Pass:** connects, arrows move the device, acks log, and it also works after you
relock/unlock the phone while the tab stays open.

---

## Test 5 — Nav end-to-end (self-routing)

This exercises the turn engine: route → GPS → auto-send.

1. On the phone, **Connect device**.
2. Search a destination **~500 m–1 km away with a few turns**, choose **🚲 Bike**.
3. Tap **▶ Go**. The map draws the route; the device shows the **first turn** with
   a distance.
4. Ride/walk the route. Expect:
   - distance on the device **counts down** (~every 50 m),
   - the arrow **blinks within ~30 m** of the turn,
   - on passing it, the device **switches to the next turn**,
   - at the destination, **`A` → ARRIVED**.
5. Tap **■ Stop** (sends `X` back to the boot screen).

**Pass:** every turn is announced before you reach it, the blink coincides with
the turn, and no turn is missed.

**Desk test (no bike):** open the app on the Mac, click **Go**, then in Chrome
DevTools → **Sensors** set the location to a point just before a turn (and step it
forward) and watch the device update.

---

## Pass criteria (quick checklist)

- [ ] Test 1: `CitiNav` advertising
- [ ] Test 2: all of `L/R/S/U/A/X`, blink, street, distance render correctly **and** ack
- [ ] Test 3: Mac web app connects, sends, logs acks
- [ ] Test 4: phone web app works over the tunnel
- [ ] Test 5: Nav announces → distance → blink → next turn → arrive

---

## Common problems

| Symptom | Fix |
|---|---|
| `CitiNav not found` | board not running (Ctrl-D/RST), already connected (close phone), or ghost connection (power-cycle) |
| No `ack` | firmware is pre-v2 → `./deploy.sh` |
| Device frozen after a reset | soft-reset ghost → hard-reset / power-cycle |
| Web app can't connect | not a secure context → use the tunnel https URL (or `localhost`) |
| Nav never moves | no GPS (allow location, be outdoors); or use DevTools Sensors override |
| Nav late/early | tune `BLINK_M` / `BUCKET_M` in `webapp/index.html` |
| Stale app after changes | bump `CACHE` in `webapp/sw.js` |
