# CitiNav — Web apps (PWA prototype)

Two installable web apps, sharing the same BLE contract:

| Page | What |
|---|---|
| **`index.html`** — **Nav** | Self-routing navigation: pick a destination on a map, **Go**, and the app tracks your GPS and **auto-sends `L/R/S`** to the device as you approach each turn. No Google Maps, no native app. |
| **`test.html`** — **Test** | The earlier prototype: map + **Start in Google Maps** handoff, plus **manual** BLE controls (`L/S/R/U/A/X`, blink, street, distance). |

Cross-linked: each has a button to the other. Manifest `shortcuts` expose both.

## 🧭 Nav (`index.html`)

**Flow:** Connect device → search/tap a destination pin → choose mode → **Go**.

- **Routing:** **Valhalla** (`valhalla1.openstreetmap.de`, free, CORS-enabled) with
  real **bicycle / pedestrian / auto** profiles and typed maneuvers.
- **Positioning:** `watchPosition` (high accuracy); a live position dot + follow.
- **Turn engine:** decodes the route polyline (precision 6), finds the next
  maneuver ahead, maps its type → `L/R/S/U/A`, and sends to the device:
  - **announces the upcoming turn** (with street + distance) as it becomes next;
  - **refreshes the distance** every ~50 m;
  - **blinks** (`LB/RB/SB`) within **30 m**;
  - sends **`A`** within **30 m** of the destination.
- **Instruction card** mirrors exactly what the device shows.

Payload grammar: `"<dir>[B][:<street>[:<dist_m>]]"`.

## 🎮 Test (`test.html`)

- **Route map** (Leaflet/OSM, Photon search, draggable pin, OSRM preview) →
  **Start in Google Maps** (`…/maps/dir/?api=1&destination=…&dir_action=navigate`).
- **Manual controls** — `◀ ▲ ▶`, `↺ U-TURN`, `⚑ ARRIVE`, `✕ CLEAR`; blink toggle;
  street (≤10) + distance; live payload preview; `ack:` log; auto-reconnect.

## Files

| File | Role |
|---|---|
| `index.html` | **Nav** app (Valhalla routing + GPS + auto-send) |
| `test.html` | **Test** app (map handoff + manual controls) |
| `manifest.json` | PWA manifest (name, colours, icons, shortcuts) |
| `sw.js` | service worker (offline shell; bump `CACHE` after edits) |
| `make_icons.py` | generates `icon-192.png` / `icon-512.png` (no deps) |
| `serve.sh` | hosts on the LAN + prints the phone instructions |
| `icon-*.png` | generated icons |

## Requirements
- **Chrome / Edge on Android or desktop.** ❌ **iOS/Safari has no Web Bluetooth.**
- Internet for map tiles, geocoding, Valhalla/OSRM and Maps. GPS + BLE need a
  **secure context** (https tunnel or `localhost`).

## Run it

### On this Mac (quickest — secure context via localhost)
```bash
cd /Users/zakaria/Documents/pi/ESP32/LCD147
./webapp/serve.sh
# open http://localhost:8000 in Chrome  (Nav)  — or /test.html (Test)
```

### On an Android phone ✅ (verified)
Web Bluetooth + geolocation need a **secure context**; `http://<mac-ip>:8000` is
not one. Use **https via a tunnel** (the tested method):

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000
```
Open the printed **https://…trycloudflare.com** URL. Then **Add to Home screen**
(PWA; the shell caches for offline).

<details>
<summary>Alternative: allow the insecure origin in Chrome (no internet)</summary>

- `python3 -m http.server 8000 --bind 0.0.0.0 --directory webapp`
- find your Mac IP: `ipconfig getifaddr en0`
- on the phone: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
  → add `http://<mac-ip>:8000` → enable → relaunch → open that URL
</details>

## Notes & limitations
- Matches the contract in `citinav_landscape.py`: Service `6e400001-…`,
  Command `6e400002-…` (write), Ack `6e400003-…` (notify).
- **Nav** computes its **own** route — it does **not** read Google Maps
  notifications (impossible in a browser). It's a self-contained navigation app;
  its turn quality is only as good as Valhalla's public demo (rate-limited, no SLA).
- **Test**'s Maps handoff covers the destination-picker UX; auto turn arrows from
  Maps still require the native Android app (`docs/CITINAV-MOBILEAPP-PLAN.md`).
- Regenerate icons after editing `make_icons.py`: `python3 webapp/make_icons.py`.
