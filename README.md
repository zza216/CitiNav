# CitiNav

*Project 3 — Emerging Tech*

**Turn-by-turn bicycle navigation on a tiny screen.** The phone is the brain; a
cheap ESP32-C6 + 1.47" LCD on the handlebars is a *dumb display* that just shows
the next turn — no need to look at the phone while riding.

```
        Phone (Chrome PWA)                      ESP32-C6 + LCD
 ┌───────────────────────────────┐   BLE   ┌───────────────────────┐
 │  • route (Valhalla)            │ ──────► │  arrow + street + dist │
 │  • GPS (watchPosition)         │  GATT   │  (landscape 3-arrow)   │
 │  • turn engine → L/R/S/U/A     │ ◄────── │  ack:<cmd>             │
 └───────────────────────────────┘   ack   └───────────────────────┘
```

## Components

| Part | What | Where |
|---|---|---|
| **Firmware** | MicroPython BLE peripheral + landscape UI | `citinav_landscape.py` |
| **Nav app** | Self-routing web app: Valhalla + GPS → auto-sends turns | `webapp/index.html` |
| **Test app** | Map picker → Google Maps handoff + manual controls | `webapp/test.html` |
| **Terminal sender** | Drive the device from a Mac | `citinav_send.py` |
| **Deploy** | Copy firmware + reboot the board | `deploy.sh` |
| **Run** | Serve the web UI + open a Cloudflare tunnel (`start`/`stop`/`status`) | `run.sh` |

## BLE contract

- Service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- Command `6e400002-…` (write) · Ack `6e400003-…` (notify)
- Payload: `<dir>[B][:<street>[:<dist_m>]]` where `dir ∈ L R S U A X`, `B` = blink.
- Ack: `ack:<cmd>`.

## Start using the UI

Four steps from a blank board to turn-by-turn arrows on the handlebars.

**1. Flash the device** (MicroPython v1.29 on the Waveshare ESP32-C6-LCD-1.47,
plugged in over USB):
```bash
./deploy.sh            # copies main.py + citinav_landscape.py + reset
```
The LCD should boot to **`CitiNav`** in yellow with a green bicycle, and the
board starts advertising over BLE.

**2. Serve the web UI — one command (server + https tunnel):**
```bash
./run.sh start     # serves webapp/ on :8000 + a Cloudflare tunnel; prints both URLs
```
It prints `http://localhost:8000` and a public `https://…trycloudflare.com` URL.
`./run.sh status` shows what's running, `./run.sh stop` shuts it down. Prefer to do
it by hand? `./webapp/serve.sh`, then
`cloudflared tunnel --url http://localhost:8000` in a second terminal.

**3. Open the UI:**
- **On the Mac** — **http://localhost:8000** in Chrome (already a secure context,
  so Web Bluetooth works).
- **On the phone** — open the printed **https://…trycloudflare.com** URL in
  **Android Chrome**.

**4. Use the UI:**
1. Tap **Connect device** → pick **`CitiNav`** in the chooser.
2. **Nav** (`index.html`) — search/tap a destination → choose **🚲 Bike** → **▶ Go**.
   The app tracks your GPS and auto-sends the turns; the LCD shows arrow + street
   + distance. Tap **■ Stop** when done.
3. **Test** (`test.html`) — manual arrows (`◀ ▲ ▶ ↺ ⚑ ✕`), blink toggle, and
   **Start in Google Maps** handoff.

> 📶 Full step-by-step — flashing, serving, the **Cloudflare Tunnel**, install-as-PWA
> and troubleshooting — is in [`docs/SETUP.md`](docs/SETUP.md). Ride-through check
> in [`docs/TESTING.md`](docs/TESTING.md).

**No phone/tunnel? Test from the Mac:**
```bash
./webapp/serve.sh          # open http://localhost:8000 in Chrome → Connect device
./citinav_send.py "L:Broadway:45"        # or drive it from the terminal
```

## Documentation

| Doc | What |
|---|---|
| [`docs/SETUP.md`](docs/SETUP.md) | **Setup guide** — flash, serve, **Cloudflare Tunnel**, connect |
| [`docs/TESTING.md`](docs/TESTING.md) | **Testing guide** — smoke test → terminal → web app → nav run |
| [`docs/CITINAV.md`](docs/CITINAV.md) | Project plan + BLE contract |
| [`docs/WEBAPP-TECHNICAL.md`](docs/WEBAPP-TECHNICAL.md) · [`.html`](docs/WEBAPP-TECHNICAL.html) | Full technical reference (HTML has all code embedded) |
| [`docs/CITINAV-MOBILEAPP-PLAN.md`](docs/CITINAV-MOBILEAPP-PLAN.md) | Native Android plan (notification mirroring) |
| [`docs/GUI-DESIGN.md`](docs/GUI-DESIGN.md) | On-device UI / RAM budget |
| [`docs/LCD-SETUP.md`](docs/LCD-SETUP.md) | Hardware bring-up |
| [`docs/TEST-CARD.md`](docs/TEST-CARD.md) | User-test card |

## Hardware

Waveshare ESP32-C6-LCD-1.47 (172×320 ST7789, SPI). Pins: SCLK 7, MOSI 6, CS 14,
DC 15, RST 21, BL 22. Firmware: MicroPython `ESP32_GENERIC_C6`.

## Status

- ✅ Firmware v2: landscape 3-arrow UI, grammar `L/R/S/U/A/X` + distance, boot splash
- ✅ Web Nav (self-routing) + Test apps (PWA)
- ⏳ Off-route reroute, battery/background, BLE pairing
