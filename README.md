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

## BLE contract

- Service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- Command `6e400002-…` (write) · Ack `6e400003-…` (notify)
- Payload: `<dir>[B][:<street>[:<dist_m>]]` where `dir ∈ L R S U A X`, `B` = blink.
- Ack: `ack:<cmd>`.

## Quick start

**Device** (MicroPython v1.29 on the Waveshare ESP32-C6-LCD-1.47):
```bash
./deploy.sh            # copies main.py + citinav_landscape.py + reset
```

**Phone app** (Chrome on Android/desktop — Web Bluetooth):
```bash
./webapp/serve.sh                        # serves on the LAN
cloudflared tunnel --url http://localhost:8000   # https for the phone
```
Open the https URL → **Connect device** → pick a destination → **Go**.

> 📶 Full step-by-step, including the **Cloudflare Tunnel** setup, is in
> [`docs/SETUP.md`](docs/SETUP.md).

**Mac quick test** (no tunnel):
```bash
./citinav_send.py "L:Broadway:45"        # left arrow + street + 45 m
```

## Documentation

| Doc | What |
|---|---|
| [`docs/SETUP.md`](docs/SETUP.md) | **Setup guide** — flash, serve, **Cloudflare Tunnel**, connect |
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
