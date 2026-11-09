# CitiNav — Project Plan (Devices + Mobile App)

*Two-part project: the **device** (ESP32-C6 + LCD) and the **mobile app** (phone).
They meet at one thing: a **BLE command interface**. This document is the shared
contract so both sides can be built and tested independently.*

**Last updated:** 05 Nov 2026

---

## 1. Overview

| Part | Owner | What it is |
|---|---|---|
| **Part 1 — Devices** | *you* | ESP32-C6 + 1.47" LCD. A "dumb display": receives `L/R/S` over BLE, shows a direction arrow (landscape 3-arrow UI v2) + street name. |
| **Part 2 — Mobile app** | *friend* | The "brain": reads GPS, computes a route, decides the next turn, and writes `L/R/S` to the device over BLE. |

The two halves only depend on the **BLE contract in §4**. Either side can be
developed and tested with a stub on the other end:

- Device side → test with the **terminal simulator** (§6) instead of the real app.
- App side → test against the device (or a fake BLE peripheral / recorded replay).

```
        PART 2 (phone / simulator)                 PART 1 (device)
   ┌──────────────────────────────┐        ┌───────────────────────────────┐
   │  GPS  ─►  route (Directions/ │        │  BLE peripheral "CitiNav"      │
   │          OSRM) ─► maneuvers   │  BLE   │   ├─ Command char (write)      │
   │              │                │ ─────► │   └─ Ack char (notify)         │
   │        next-turn logic        │        │            │                   │
   │     writes  "L" / "R" / "S"   │ ◄───── │            ▼                   │
   └──────────────────────────────┘  ack   │      LCD: arrow + street name  │
                                           └───────────────────────────────┘
```

---

## 2. Design principle (from the prototype guide)

> **The phone is the brain. The ESP32 is a dumb display.**

All routing, GPS and decision-making live on the phone. The device only:
1. Advertises over BLE,
2. Accepts a short direction command,
3. Renders it.

This keeps the device cheap, simple and replaceable.

---

# PART 1 — DEVICES (you)

## 3. Hardware

| Item | Detail |
|---|---|
| Board | **Waveshare ESP32-C6-LCD-1.47** (sold as "Wonrabai" on Amazon) |
| Chip | ESP32-C6FH8 (QFN32), 8 MB flash, Wi-Fi 6 + BLE 5 + 802.15.4 |
| Display | 1.47" IPS, 172×320, ST7789, SPI |
| Firmware | MicroPython v1.29.0 (`ESP32_GENERIC_C6`) |

**Onboard LCD pins (fixed):**

| Signal | GPIO |
|---|---|
| SCLK | 7 |
| MOSI (DIN) | 6 |
| CS | 14 |
| DC | 15 |
| RST | 21 |
| BL | 22 |

## 4. Firmware (this repo)

| File | Role |
|---|---|
| `main.py` | launcher → runs `citinav_landscape.main()` on boot |
| `citinav_landscape.py` | **active firmware (UI v2)**: BLE peripheral + landscape 3-arrow UI |
| `citinav.py` | portrait firmware (UI v1) — kept as fallback |
| `deploy.sh` | copy firmware to the board + reboot (`./deploy.sh`) |
| `st7789py.py` | LCD driver (proven) |
| `vga1_8x16.py` | small font (bottom label) |
| `vga2_bold_16x32.py` | large font (street name / boot title) |

**Behaviour**
- Advertises as **`CitiNav`**.
- Boots to a splash: **`CitiNav`** in yellow on dark grey (nothing else).
- Panel is rotated to **landscape (320×172)** for the command screen.
- On a command it shows **three arrows in a horizontal row** (left · straight ·
  right): the commanded one is highlighted **green** and boxed, the others are
  dimmed. `LB`/`RB`/`SB` blink the active arrow.
- A street name (when sent) shows in the top banner; the label
  (`TURN LEFT` / `TURN RIGHT` / `GO STRAIGHT`) shows at the bottom.
- Queues commands so rapid bursts are not lost (300 ms minimum on-screen hold).
- Replies with `ack:<cmd>` on the ack characteristic and re-advertises after disconnect.

**UI v2 layout (landscape, green on dark grey)**

```
 boot / idle              command  (e.g. R:Broadway)
┌────────────────┐      ┌──────────────────────────────┐
│                │      │           Broadway           │  banner (bigfont)
│                │      ├──────────────────────────────┤
│    CitiNav     │      │   ◄       ▲       ►          │  ◄ dim   ▲ dim
│    (yellow)    │      │  dim    green    dim          │  ► green + box
│                │      ├──────────────────────────────┤
│                │      │         TURN RIGHT           │  label
└────────────────┘      └──────────────────────────────┘
```

**Street names**

The banner text now comes **from the app / sender** over BLE (see §5.5):
`L:W 4th St`, `R:Broadway`, `S:5th Ave`. Nothing is hardcoded on the device —
`citinav_send.py` provides the street text.

---

## 5. BLE interface contract  ⭐ (the agreement)

Both teams build to **this** spec.

### 5.1 Advertising
- Device name: **`CitiNav`**
- Service UUID advertised (scan response)

### 5.2 GATT — Nordic UART Service UUIDs

| Role | UUID | Properties |
|---|---|---|
| **Service** | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | — |
| **Command** (app → device) | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | WRITE, WRITE_NO_RESPONSE, READ |
| **Ack** (device → app) | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | READ, NOTIFY |

### 5.3 Command payload (write to `…0002`)

Grammar (kept in sync with the mobile-app plan §6.1):

```
<dir>[B][:<street>[:<dist_m>]]
```

| `dir` | Meaning | Device shows |
|---|---|---|
| `L` | turn left | left arrow highlighted (3-arrow row) + "TURN LEFT" |
| `R` | turn right | right arrow highlighted + "TURN RIGHT" |
| `S` | straight / continue | straight arrow highlighted + "GO STRAIGHT" |
| `U` | U-turn | U-turn glyph + "U-TURN" |
| `A` | arrive | "ARRIVED" screen |
| `X` | clear / idle | `CitiNav` boot screen |

- `B` after `L`/`R`/`S`/`U` = **blink**: `LB`, `RB`, `SB`, `UB`
- `street` (optional) → top banner, ASCII, truncated to 10 chars
- `dist_m` (optional, integer metres) → appended to the bottom label
- Examples: `L`, `RB`, `U`, `A`, `X`, `L:W 4th St`, `LB:W 4th St:30`

- Case-insensitive; street/dist keep their case.
- Unknown first char → ignored (logged on device console).
- Short ASCII string, well under the default 20-byte ATT payload (no MTU negotiation needed).
- Status: `L`/`R`/`S` + street **verified**; `U`/`A`/`X` + `dist` implemented in
  `citinav_landscape.py` (§11 — deploy pending).

### 5.4 Ack payload (notify on `…0003`)

After handling a command the device writes and notifies:

```
ack:<cmd>        e.g.  "ack:L"  or  "ack:RB"
```

Use this to measure BLE round-trip latency (see guide's risk test).

### 5.5 Street name from the app — implemented (Option A)

The device shows the *real* next street sent by the app, not a mock.

- **Option A (keep 1 characteristic):** command = `"<dir>[B][:<street>[:<dist_m>]]"`,
  e.g. `"L:W 4th St"`, `"R:Broadway"`, `"LB:W 4th St:30"`.
  Device splits on `:`, uses `dir` for the arrow, `street` for the banner
  (truncated to 10 chars) and `dist_m` for the distance. ✅ **chosen and implemented.**
- **Option B (new characteristic):** add a separate *Street* characteristic
  (write) so text and direction update independently. *(not used)*

---

# PART 2 — MOBILE APP (friend)

## 6. App responsibilities

1. **Get location** continuously (GPS).
2. **Compute a route** with maneuvers:
   - Google **Directions API** (`mode=bicycling`) — pay-as-you-go, or
   - **OSRM / Valhalla / GraphHopper** — free, no key (good for a prototype).
3. **Map each step** to a command:

   ```python
   def to_cmd(maneuver):
       if maneuver and "left"  in maneuver: return "L"
       if maneuver and "right" in maneuver: return "R"
       return "S"        # straight / merge / depart / arrive
   ```

4. **Run the nav loop:** find the current step, measure distance to its
   `end_location`; when within the **trigger distance (~30 m)**, connect once and
   **write** the command to the Command characteristic.
5. **Optionally** blink (`LB/RB/SB`) for imminent turns, and read the **ack**
   to log latency.

**Suggested stacks**
- **Flutter** — `flutter_blue_plus` + `geolocator` + `http`
- **Android (Kotlin)** — `BluetoothGatt` + `FusedLocationProvider`
- **iOS (Swift)** — `CoreBluetooth` + `CoreLocation` (needs "Always" permissions)

> ⚠️ iOS is the most restricted; plan for background BLE + location caveats.

## 7. Timing / tuning
- Send the turn **~30 m early** to cover BLE + processing latency.
- Re-use one BLE connection for the whole trip (don't reconnect per turn).
- Trigger on **distance to the maneuver**, not on a timer.

---

# TERMINAL SIMULATOR (stand-in for the app)

Because Part 2 isn't built yet, we test the device with a **terminal simulator
that plays the role of the app**.

## 8. Current tool — manual sender

`citinav_send.py` (uses `bleak`) — connects to `CitiNav` and writes commands.

```bash
cd /Users/zakaria/Documents/pi/ESP32/LCD147
./citinav_send.py                 # interactive
./citinav_send.py L RB S          # one-shot arrows
./citinav_send.py LB              # blinking left
./citinav_send.py "L:W 4th St" "R:Broadway"   # arrows + street text
```

```
cmd> L:W 4th St   → sent L:W 4th St
cmd> RB           → sent RB
cmd> Q            → disconnect
```

Use `;` to send several commands on one line, e.g. `L:W 4th St ; RB`.

This already **proves the whole chain**: sender → BLE → device → LCD.

### Web Bluetooth simulator (graphical — runs from a phone)

`webapp/` is a single-page **Web Bluetooth** app that does the same job as the
terminal sender but with a touch UI — Connect, tap ◀ ▲ ▶, tick **Blink**, type a
street name, and watch the `ack:` log.

```bash
cd /Users/zakaria/Documents/pi/ESP32/LCD147
./webapp/serve.sh                       # serves http://<mac-ip>:8000
# phone needs a SECURE origin (https), so tunnel it:
brew install cloudflared
cloudflared tunnel --url http://localhost:8000   # open the https URL on the phone
```

- Works in **Chrome on Android / desktop**. ❌ **iOS/Safari has no Web Bluetooth**
  (iPhone needs the native app — §6).
- Web Bluetooth requires a **secure context**: the Mac's `localhost` is fine; the
  phone uses the tunnel https URL (or Chrome's
  `#unsafely-treat-insecure-origin-as-secure` flag on the LAN IP).
- ✅ **Verified end-to-end from an Android phone via a cloudflared tunnel.**

Details: `webapp/README.md`.

## 9. Planned tool — navigation simulator

A bigger terminal script that mimics the app end-to-end:

1. Fetch a route with maneuvers (OSRM public server — **no API key**).
2. Convert maneuvers → `L/R/S` sequence.
3. **Walk a virtual position** along the route geometry at a chosen speed.
4. When within ~30 m of a turn, send the command over BLE (auto).
5. Print a live "navigation" log; optionally measure ack latency.

```
$ ./citinav_nav_sim.py --from "40.7295,-73.9965" --to "40.7580,-73.9855"
route: 4.2 km, 12 steps
  step 3: turn-left  → within 30 m … sent L   (ack 41 ms)
  step 4: turn-right → within 30 m … sent R   (ack 38 ms)
  ...
```

This lets **Part 1 be fully validated** without a phone, and gives Part 2 a
reference implementation to copy.

---

## 10. Work split & workflow

| | Part 1 — Device (you) | Part 2 — App (friend) |
|---|---|---|
| Build | firmware, UI, BLE peripheral | GPS, routing, BLE central |
| Test with | **terminal simulator** | real device (or recorded replay) |
| Depends on | the BLE contract (§5) | the BLE contract (§5) |

**Agree on §5 first** (especially the street-name extension §5.5). After that,
both sides progress independently.

---

## 11. Status & roadmap

**Stage 1 — COMPLETE ✅**
- [x] LCD bring-up (172×320 ST7789)
- [x] BLE peripheral with Nordic-UART UUIDs
- [x] Arrows + street name + blink
- [x] Street name sent over BLE (Option A §5.5 → `<dir>:<street>`), not hardcoded
- [x] Command queue + ack
- [x] Terminal sender verified from the Mac (arrows + street text)

**UI v2 — COMPLETE ✅ (landscape)**
- [x] Landscape rotation (320×172)
- [x] Three-arrow horizontal layout; commanded arrow highlighted, others dimmed
- [x] Green arrows on a dark-grey background
- [x] Yellow `CitiNav` boot splash (no black text boxes — text uses the region colour)
- [x] Device sends `ack:<cmd>` notifications
- [x] `deploy.sh` one-shot deploy + reboot (avoids the mpremote `cp`/`reset` trap)

**Mobile simulator — COMPLETE ✅ (Android, Web Bluetooth PWA)**
- [x] `webapp/` — Web Bluetooth app: scan/connect `CitiNav`, tap `L/S/R`, blink, street name, ack log
- [x] Full §6 grammar UI: `U`/`A`/`X` + distance, prefs (localStorage), auto-reconnect, vibration
- [x] Installable **PWA**: `manifest.json` + `sw.js` + generated icons (`make_icons.py`)
- [x] `webapp/serve.sh` (LAN host) + **cloudflared** https tunnel
- [x] Verified end-to-end from an Android phone's Chrome

**Firmware grammar v2 — COMPLETE ✅**
- [x] `citinav_landscape.py` parses `U`/`A`/`X` + `dist_m`; U-turn, ARRIVED and clear (idle) screens
- [x] Deployed and verified on device
- [x] Re-advertising moved out of the BLE IRQ (fixes `OSError -30`); retried in the main loop with `gap_advertise(None)` first
- [ ] Note: a soft reset while a central is connected can leave a *ghost* connection — hard-reset/power-cycle to clear

**Web app v3 — Test (map + manual) — COMPLETE ✅ (prototype)**
- [x] Map (Leaflet/OSM): Photon search, draggable pin, geolocation, OSRM preview
- [x] Travel mode → **Start in Google Maps** deep-link handoff
- [x] Manual controls (`L/S/R/U/A/X`, blink, street, distance, ack log), auto-reconnect
- [x] Kept as `webapp/test.html` for the initial test prototype

**Web app v4 — Nav (self-routing) — COMPLETE ✅ (prototype)**
- [x] **Valhalla** routing (bicycle/pedestrian/auto) + `watchPosition`
- [x] Auto-sends `L/R/S/U/A` with street + distance; blinks within 30 m; `A` at arrival
- [x] Decodes the route polyline; on-screen instruction card mirrors the device
- [x] `webapp/index.html` = Nav, `webapp/test.html` = Test (cross-linked, PWA shortcuts)
- [ ] Field test on a real ride; tune thresholds / Valhalla demo reliability

**Stage 2 — NEXT**
- [x] Protocol extension for real street names (§5.5, Option A)
- [ ] Build the **navigation simulator** (§9)
- [ ] App team builds GPS + route + BLE loop (Part 2)
- [ ] Integration test (app ↔ device)
- [ ] Latency / reliability measurement (via ack)

---

## 12. File reference

| Path | What |
|---|---|
| `main.py` | boot launcher → runs `citinav_landscape.main()` |
| `citinav_landscape.py` | **active device firmware (UI v2)**: landscape 320×172, three horizontal arrows, green-on-dark-grey |
| `citinav.py` | portrait firmware (v1) — kept as fallback |
| `citinav_send.py` | terminal sender / simulator (arrows + street text) |
| `webapp/` | **Web Bluetooth mobile simulator (PWA)**: `index.html`, `manifest.json`, `sw.js`, `icon-*.png`, `make_icons.py`, `serve.sh`, `README.md` |
| `deploy.sh` | copy firmware to the board + reboot (`./deploy.sh`) |
| `citinav_nav_sim.py` | *(planned)* navigation simulator |
| `st7789py.py`, `vga1_8x16.py`, `vga2_bold_16x32.py` | LCD driver + fonts |
| `LCD-SETUP.md` | LCD hardware/setup notes |
| `/dev/cu.usbmodem101` | device serial port (mpremote) — varies by USB port, see `mpremote devs` |
| `~/.esptool-venv` | venv with `esptool`, `mpremote`, `bleak` |
