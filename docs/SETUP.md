# CitiNav — Setup Guide

*End-to-end: flash the device, serve the web app, expose it to your phone over a
**Cloudflare Tunnel**, and connect.*

**Why a tunnel?** Web Bluetooth and Geolocation only work in a **secure context**
(`https://` or `localhost`). A page served at `http://<mac-ip>:8000` is *not*
secure, so Chrome on the phone blocks them. A Cloudflare **quick tunnel** gives a
free `https://…trycloudflare.com` URL that proxies to your Mac — no account, no
certificate.

```
 Mac (host)                                    Android phone (Chrome)
 ┌────────────────────────────┐  https proxy   ┌───────────────────────────┐
 │ ./webapp/serve.sh          │ ◄────────────► │ https://…trycloudflare.com │
 │   python -m http.server    │                │  • loads the PWA           │
 │ cloudflared tunnel --url   │                │  • Web Bluetooth → CitiNav │
 │   http://localhost:8000    │                │  • Geolocation (Nav)       │
 └────────────────────────────┘                └───────────────────────────┘
                                                        │ BLE
                                                        ▼
                                              ESP32-C6 + LCD (citinav_landscape.py)
```

> The tunnel only *delivers the page*. Once loaded, BLE traffic is phone ↔ device
> and never leaves the phone.

---

## 0. Prerequisites

- **Mac** with the board connected over USB for flashing (data-capable cable).
- **ESP32-C6-LCD-1.47** flashed with MicroPython v1.29 (`ESP32_GENERIC_C6`).
- Python venv at `~/.esptool-venv` with `esptool`, `mpremote`, `bleak`.
- **Android phone** with **Chrome** (iOS/Safari has no Web Bluetooth).
- `brew` for installing `cloudflared`.

---

## A. Flash the device

```bash
cd /Users/zakaria/Documents/pi/ESP32/LCD147
~/.esptool-venv/bin/mpremote devs        # find the /dev/cu.usbmodem* port
./deploy.sh                              # auto-detects the port, copies firmware, reboots
```

`deploy.sh` copies `main.py`, `citinav_landscape.py`, `citinav.py` and resets the
board. You should see **`CitiNav` in yellow with a green bicycle** on the LCD, and
the board advertising over BLE.

> If the board is unplugged or only on BLE, `deploy.sh` can't run — plug in USB.

---

## B. Serve the web app on the Mac

```bash
./webapp/serve.sh            # binds 0.0.0.0:8000 and prints the URLs
```
- On the Mac: **http://localhost:8000** (already a secure context → works now).
- It also prints the LAN URL and the secure-context options.

Keep this terminal running.

---

## C. Expose it to the phone with a Cloudflare Tunnel  ← the key step

In a **second** terminal:

```bash
brew install cloudflared                              # once
cloudflared tunnel --url http://localhost:8000
```

It prints a line like:

```
Your quick Tunnel has been created! Visit it at:
https://random-words-1234.trycloudflare.com
```

That **https://…trycloudflare.com** URL is the address you open on the phone.
Needs the Mac online; the URL **changes each time** you restart the tunnel.

---

## D. Open it on the phone

1. Make sure the phone is on **the same Wi-Fi** as the Mac (not required for the
   tunnel, but simpler troubleshooting).
2. In **Chrome**, open the **https://…trycloudflare.com** URL.
3. Tap **Connect device** → pick **`CitiNav`** in the chooser.
4. Use the app:
   - **Nav**: pick a destination on the map → **🚲 Bike** → **▶ Go**.
   - **Test**: pick a destination → **Start in Google Maps**, or use the manual
     arrow buttons.
5. Optional: Chrome menu → **Add to Home screen** to install the PWA (the service
   worker caches the shell so it opens offline; the tunnel is only needed to load
   the page the first time).

---

## Alternative secure-context methods (no tunnel)

<details>
<summary>Ngrok</summary>

```bash
npx ngrok http 8000        # open the printed https URL on the phone
```
</details>

<details>
<summary>Chrome "insecure origin" flag (offline, no cert)</summary>

Web Bluetooth needs an allowlisted origin:
- `python3 -m http.server 8000 --bind 0.0.0.0 --directory webapp`
- get your Mac IP: `ipconfig getifaddr en0`
- on the phone: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
  → add `http://<mac-ip>:8000` → **Enabled** → relaunch Chrome → open that URL.
</details>

<details>
<summary>Local HTTPS with mkcert</summary>

Create a locally-trusted cert and serve `webapp/` over https; install the mkcert
root CA on the phone. More setup, fully offline.
</details>

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connect device` fails / no chooser | page not a secure context | use the tunnel https URL (or localhost) |
| Board not found in the chooser | another client is connected (your phone/Mac) | disconnect the other client — a peripheral can't advertise while connected |
| Board not advertising at all | *ghost* connection after a soft reset | hard-reset / power-cycle the board |
| Tunnel URL stopped working | quick-tunnel URL rotates | restart `cloudflared` and open the new URL |
| Map/search blank | no internet for tiles/Photon | check connectivity |
| `ack` never arrives | old firmware (pre-v2) | re-run `./deploy.sh` |
| App looks stale after updates | service worker cache | bump `CACHE` in `webapp/sw.js` |

---

## Quick reference

```bash
# 1. flash
./deploy.sh

# 2. serve (Mac)
./webapp/serve.sh

# 3. tunnel (2nd terminal)
cloudflared tunnel --url http://localhost:8000
#    → open the https://…trycloudflare.com URL on the phone's Chrome

# 4. quick Mac test without a phone
./citinav_send.py "L:Broadway:45"
```
