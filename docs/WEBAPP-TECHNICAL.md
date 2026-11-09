# CitiNav Web App — Technical Reference

*How the browser-based CitiNav apps work: architecture, the BLE contract, the
navigation engine, the firmware, and the end-to-end data flow.*

**Audience:** anyone maintaining or extending the web apps or the device
firmware. For the product plan see [`CITINAV.md`](CITINAV.md) and
[`CITINAV-MOBILEAPP-PLAN.md`](CITINAV-MOBILEAPP-PLAN.md).

> 📄 A **self-contained HTML version with all source code embedded** is at
> [`WEBAPP-TECHNICAL.html`](WEBAPP-TECHNICAL.html). Rebuild it after editing this
> file with `python3 docs/build_html.py`.

---

## 1. Purpose & scope

CitiNav is a **dumb display**: an ESP32-C6 with a 1.47" LCD that renders a
direction arrow + street name. A phone is the "brain". This document covers the
**web implementation of the brain**:

| App | File | Role |
|---|---|---|
| **Nav** | `webapp/index.html` | Self-routing navigation: computes a route, tracks GPS, and **auto-sends** turn commands to the device. |
| **Test** | `webapp/test.html` | Map destination picker + **Google Maps handoff**, plus **manual** BLE controls. |

Both speak the same BLE contract (§3) and run in **Chrome on Android/desktop**
(Web Bluetooth is unavailable on iOS).

---

## 2. System architecture

### 2.1 Context

```
                         ┌──────────────────────────────┐
                         │  External services (HTTPS)    │
                         │  • Valhalla  (routing)        │
                         │  • Photon    (geocoding)      │
                         │  • OSM tiles (map)            │
                         │  • Google Maps (handoff)      │
                         └───────────────▲──────────────┘
                                         │ fetch / open
 ┌────────────────────┐   HTTPS (page)   │
 │  Mac (host)        │◄────────────────┐│
 │  serve.sh          │                 ││
 │  python http.server│   cloudflared   ││
 │  :8000             │◄───tunnel──────►││
 └────────────────────┘                 ││
                              ┌─────────┴┴──────────────┐
                              │  Phone — Chrome (PWA)    │
                              │  • Nav / Test app        │
                              │  • Web Bluetooth (GATT)  │
                              │  • Geolocation           │
                              └───────────┬──────────────┘
                                          │ BLE (GATT write / notify)
                                          ▼
                              ┌──────────────────────────┐
                              │  ESP32-C6 + ST7789 LCD    │
                              │  citinav_landscape.py     │
                              └──────────────────────────┘
```

**Key point:** the tunnel only *delivers the page*. Once loaded, BLE traffic is
phone ↔ device and never leaves the phone. Routing/geocoding calls go directly
from the phone to the public services.

### 2.2 Components

| Component | Responsibility |
|---|---|
| `webapp/index.html` | Nav app: map, routing, GPS loop, turn engine, BLE client |
| `webapp/test.html` | Test app: map picker, Maps handoff, manual BLE controls |
| `webapp/manifest.json` | PWA metadata (name, colours, icons, shortcuts) |
| `webapp/sw.js` | Service worker: offline app-shell cache |
| `webapp/make_icons.py` | Generates PNG icons (no dependencies) |
| `webapp/serve.sh` | LAN host + prints phone/secure-context instructions |
| `citinav_landscape.py` | Device firmware: BLE peripheral + LCD UI |
| `deploy.sh` | Copies firmware to the board and reboots |

### 2.3 Why a tunnel (secure context)

Web Bluetooth **and** Geolocation require a **secure context** (`https://` or
`localhost`). A page served at `http://<mac-ip>:8000` is not secure, so Chrome
blocks both APIs. A **Cloudflare quick tunnel** provides a temporary
`https://…trycloudflare.com` origin that proxies to the Mac — no account, no
certificate. Alternatives: a named tunnel + domain, `mkcert` local CA, or
Chrome's `#unsafely-treat-insecure-origin-as-secure` flag.

---

## 3. The BLE contract

Both apps and the firmware implement this contract. It is the single source of
truth shared with the native-app plan (§6 of `CITINAV-MOBILEAPP-PLAN.md`).

### 3.1 GATT (Nordic UART Service UUIDs)

| Role | UUID | Properties |
|---|---|---|
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | — |
| Command (app → device) | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | WRITE, WRITE_NO_RESPONSE, READ |
| Ack (device → app) | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | READ, NOTIFY |

- Advertised name: **`CitiNav`** (the app filters on `namePrefix: "CitiNav"`).
- The service UUID is in the scan response, so `optionalServices` must list it.

### 3.2 Command payload grammar

```
<dir>[B][:<street>[:<dist_m>]]
```

| `dir` | Meaning | Device screen |
|---|---|---|
| `L` | turn left | 3-arrow row, left highlighted |
| `R` | turn right | 3-arrow row, right highlighted |
| `S` | straight / continue | 3-arrow row, straight highlighted |
| `U` | U-turn | U-turn glyph |
| `A` | arrive | "ARRIVED" |
| `X` | clear / idle | `CitiNav` boot screen |

- `B` after `L/R/S/U` = **blink** (`LB`, `RB`, `SB`, `UB`).
- `street` → top banner, ASCII, truncated to **10 chars**.
- `dist_m` → appended to the bottom label (`TURN LEFT  30m`).
- Examples: `L`, `RB`, `U`, `A`, `X`, `L:W 4th St`, `LB:W 4th St:30`.
- Total payload stays **≤ 20 bytes** (no MTU negotiation needed).

### 3.3 Ack

After handling a command the device notifies `ack:<cmd>` on the ack
characteristic, e.g. `ack:L`, `ack:RB`. The apps log it; it is also a cheap
round-trip latency probe.

### 3.4 Connection lifecycle

```
app                                   device
 │  scan (namePrefix CitiNav)           │ advertising
 │ ───────────────────────────────────►│
 │  connect (GATT)                      │
 │ ───────────────────────────────────►│  IRQ: CENTRAL_CONNECT
 │  getPrimaryService / getCharacteristic
 │  startNotifications(ack)             │
 │  writeValueWithResponse(cmd)         │  IRQ: GATTS_WRITE → queue
 │ ◄─────────────────────────────────── │  notify "ack:<cmd>"
 │  ...                                 │
 │  disconnect                          │  IRQ: CENTRAL_DISCONNECT
 │                                      │  → need_advertise = True
 │                                      │  → main loop re-advertises
```

> **Ghost-connection caveat:** a *soft* reset (Ctrl-D / `mpremote reset`) while a
> central is connected can leave the ESP32 controller holding a stale link, so
> the device neither advertises nor accepts. A **hard reset / power-cycle**
> clears it. The firmware also defers re-advertising out of the IRQ (§7.5).

---

## 4. Web app architecture

### 4.1 Files & PWA shell

```
webapp/
├── index.html      Nav app (main)
├── test.html       Test app (kept prototype)
├── manifest.json   PWA manifest + shortcuts (Nav, Test)
├── sw.js           service worker (cache-first app shell)
├── make_icons.py   icon generator
├── icon-192.png
├── icon-512.png
├── serve.sh        LAN host
└── README.md
```

- **Manifest** — `display: standalone`, dark theme, `shortcuts` to both apps.
- **Service worker** — on `install`, caches `./`, `index.html`, `test.html`,
  `manifest.json`, icons. On `fetch`, serves from cache first, else network, and
  caches new GETs; falls back to `index.html` offline. **Bump `CACHE`** (e.g.
  `citinav-v3`) whenever the shell changes so clients update.
- **Cross-links** — each app links to the other; the manifest exposes both.

### 4.2 Hosting

`serve.sh` runs `python3 -m http.server <port> --bind 0.0.0.0` in `webapp/` and
prints the Mac URL, the LAN URL, and the secure-context options. The phone loads
the page through the tunnel; the Mac can use `http://localhost:<port>` directly.

---

## 5. Nav app (`index.html`)

### 5.1 Data flow

```
 destination (search / pin)
        │
        ▼
 ┌──────────────┐   POST /route    ┌───────────────────────────────┐
 │  Valhalla    │◄────────────────►│ { shape (polyline), maneuvers }│
 └──────────────┘                  └───────────────┬───────────────┘
                                                   │ decodePolyline()
                                                   ▼
                                          routeShape[] (lat,lng)
                                                   │
 GPS watchPosition ──► nearestIndex() ──► nextManeuverIndex()
        │                                          │
        │                                          ▼
        │                                   dirForType(type)
        │                                          │
        └──────────────► payload builder ──► BLE write ──► device
```

### 5.2 Routing (Valhalla)

`go()` posts to `https://valhalla1.openstreetmap.de/route`:

```json
{
  "locations": [ {"lat": <me>, "lon": <me>}, {"lat": <dest>, "lon": <dest>} ],
  "costing": "bicycle",                       // bicycle | pedestrian | auto
  "directions_options": { "units": "kilometers" }
}
```

Response used: `trip.legs[0].shape` (encoded polyline, precision **6**) and
`trip.legs[0].maneuvers[]`. Each maneuver has `type`, `instruction`,
`street_names[]`, `length` (km), `begin_shape_index`, `end_shape_index`.

> The public OSRM demo ignores the profile (car-only), which is why Nav uses
> Valhalla for real bicycle/pedestrian routing. Both are CORS-enabled.

### 5.3 Polyline decoding

Valhalla returns a Google-encoded polyline at **1e6** precision. `decodePolyline`
walks the string, delta-decodes lat/lng, and returns `[[lat,lng], …]`. Verified
against live data: first point snaps to the road near the origin, last point
equals the destination.

### 5.4 Maneuver model & direction mapping

`dirForType(type)` maps Valhalla maneuver types to device directions:

| Device dir | Valhalla types |
|---|---|
| `A` arrive | 4 destination, 5 dest-right, 6 dest-left |
| `U` u-turn | 12 u-turn-right, 13 u-turn-left |
| `R` right | 9 slight-right, 10 right, 11 sharp-right, 18 ramp-right, 20 exit-right, 23 stay-right, 37 merge-right |
| `L` left | 14 sharp-left, 15 left, 16 slight-left, 19 ramp-left, 21 exit-left, 24 stay-left, 38 merge-left |
| `S` straight | everything else (start, continue, becomes, stay-straight, merge, roundabout, …) |

### 5.5 Progress tracking

- `nearestIndex(p)` — nearest route vertex to the current position. It starts
  scanning at `curIdx-5` (monotonic progress) and stops once the distance grows
  `> bestD + 200 m` (moved past the nearest point). O(route length) worst case,
  cheap in practice.
- `nextManeuverIndex(idx)` — first maneuver whose `begin_shape_index > idx`
  (i.e. the next turn ahead); falls back to the last maneuver (arrival).
- Distance to the turn = `haversine(position, routeShape[begin_shape_index])`.

### 5.6 Command-emission state machine

```
                 j changes (new upcoming turn)
        ┌───────────────────────────────────────────┐
        ▼                                           │
   ANNOUNCE  ──write(dir:street:dist)──►  APPROACH   │
        ▲                                   │        │
        │ bucket changes (dist/50 m)        │ dist ≤ BLINK_M (30 m)
        └───────────write(updated dist)─────┤        │
                                            ▼        │
                                          BLINK ─────┘
                                     write(dirB:street:dist)
        (turn passed → j advances → ANNOUNCE again)
```

Rules in `onPos()`:

| Condition | Action |
|---|---|
| `j` changed (new upcoming maneuver) | send **static** `dir:street:dist`; reset blink flag |
| `floor(dist/50)` changed | re-send **static** with updated distance |
| `dist ≤ 30 m` and not yet blinked for `j` | send **blink** `dirB:street:dist` |
| `dir == A` and `dist ≤ 30 m` | send `A` once |

`payload(blink)` builds the string:

```js
dir + (blink && dir in {L,R,S,U} ? "B" : "")
    + (street || dist != null ? ":" + street : "")
    + (dist != null ? ":" + dist : "")
```

### 5.7 Pseudocode

```
go():
  require dest
  ensure userLatLng (geolocate if needed)
  route = POST Valhalla(me, dest, costing)
  routeShape = decodePolyline(route.shape)
  maneuvers  = route.maneuvers
  draw polyline; fitBounds; follow = true
  reset curIdx, lastAnnounced, lastBucket, blinkedFor
  watchId = watchPosition(onPos, highAccuracy)

onPos(pos):
  update user marker (follow → recenter)
  if not navigating: return
  curIdx = nearestIndex(pos)
  j = nextManeuverIndex(curIdx)
  m = maneuvers[j]; dist = haversine(pos, shape[m.begin_shape_index])
  dir = dirForType(m.type); street = m.street_names[0][:10]
  update instruction card
  if dir == A: if dist<=30 and new: write("A"); return
  if j changed or bucket changed: write(static payload)
  if dist<=30 and not blinked: write(blink payload)

stop(): clearWatch; optionally write("X")
```

### 5.8 Sequence (one turn)

```
GPS        Nav app                         Device
 │ pos      │                               │
 │─────────►│ nearestIndex / nextManeuver   │
 │          │ dist=180m, j=3 (left)         │
 │          │── write "L:Broadway:180" ────►│ shows TURN LEFT 180m
 │ pos      │                               │
 │─────────►│ bucket 3→2 (dist 140m)        │
 │          │── write "L:Broadway:140" ────►│ updates distance
 │ pos      │                               │
 │─────────►│ dist=28m                      │
 │          │── write "LB:Broadway:28" ────►│ blinks left
 │ pos      │                               │
 │─────────►│ j advances to 4 (right)       │
 │          │── write "R:5th Ave:220" ─────►│ shows TURN RIGHT 220m
```

---

## 6. Test app (`test.html`)

The earlier prototype, kept for the initial test flow.

### 6.1 Map & destination

- **Leaflet + OpenStreetMap** tiles; a **draggable marker**; tap the map to move
  it. `setDest(lat,lng,name)` updates the label and reverse-geocodes if unnamed.
- **Search** — Photon (`photon.komoot.io/api`) with a 450 ms debounce; results
  are buttons that recenter the map and set the destination.
- **Reverse geocode** — Photon `/reverse` when the pin is dragged.
- **Route preview** — OSRM `/route/v1/driving/...` draws a green polyline and
  shows km/min (best-effort; car profile).

### 6.2 Google Maps handoff

`startMaps()`:

1. Sends `S:<destination>` to the device (banner preview) if connected.
2. Opens
   `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>&travelmode=<mode>&dir_action=navigate`
   where `mode` ∈ `bicycling | walking | driving`.

> A web app **cannot read Google Maps' navigation notifications**, so it cannot
> auto-send turns from Maps. That requires the native Android app
> (`NotificationListenerService`). The Test app is a manual/handoff prototype.

### 6.3 Manual controls

`◀ ▲ ▶` → `L/S/R`; `↺ U-TURN / ⚑ ARRIVE / ✕ CLEAR` → `U/A/X`; **Blink** toggle;
**Street** (≤10) + **distance**; live payload preview; `ack:` log; auto-reconnect
with exponential backoff (1 s → 15 s).

---

## 7. Firmware (`citinav_landscape.py`)

### 7.1 Boot sequence

```
main()
 ├─ lcd_setup()      SPI + ST7789, rotation=1 (landscape 320×172)
 ├─ show_idle()      "CitiNav" in yellow on dark grey
 ├─ ble_setup()      BLE active, GATT service, advertise()
 └─ loop:
      ├─ re-advertise if needed (deferred from IRQ)
      ├─ pop command queue (respect HOLD_MS)
      ├─ render screen + notify ack
      └─ blink active arrow every BLINK_MS
```

### 7.2 BLE setup & IRQ

- `ble_setup()` registers the service/characteristics, writes `ready` to the ack
  characteristic, installs `irq`, and advertises.
- `irq()` handles three events:
  - `CENTRAL_CONNECT` → add to `connections`.
  - `CENTRAL_DISCONNECT` → remove; **set `need_advertise = True`** (do *not*
    call `advertise()` here — see §7.5).
  - `GATTS_WRITE` → read the command characteristic, parse, enqueue.

### 7.3 Command parsing

```python
parts  = txt.split(":", 2)
head   = parts[0].strip().upper()          # e.g. "LB"
street = parts[1].strip() if len>1 else None
dist   = parts[2].strip() if len>2 else None
d      = head[:1]                          # "L"
if d in ("L","R","S","U","A","X"):
    blink = len(head) > 1 and head[1] == "B"
    cmd   = d + ("B" if blink else "")
    cmd_queue.append((cmd, street, dist, conn))
```

### 7.4 Main loop & rendering

- **Queue** — FIFO; a new command is shown only after `HOLD_MS` (300 ms) so
  bursts are not lost.
- **Screens**:
  - `show_dir` — banner + label + **three-arrow row** (`L · S · R`); the active
    arrow is green + boxed, the others dimmed.
  - `show_uturn` — banner + label + U-turn glyph.
  - `show_arrive` — banner + "ARRIVED".
  - `show_idle` — `CitiNav` splash.
- **Blink** — every `BLINK_MS` (300 ms) the active arrow toggles; the box stays.
- **Ack** — `ble.gatts_notify(conn, st_handle, b"ack:" + cmd)` (best-effort).

### 7.5 Re-advertise fix (important)

Calling `gap_advertise()` **inside the BLE IRQ** raised `OSError(-30)` and could
wedge the stack. The fix:

```
IRQ (disconnect):  need_advertise = True
main loop:         if need_advertise and now >= adv_retry_at:
                       try: advertise(); need_advertise = False
                       except: adv_retry_at = now + 500ms   # retry
advertise():       gap_advertise(None)   # stop any stale advertising
                   gap_advertise(100000, adv_data, resp_data)
```

### 7.6 Firmware main-loop flowchart

```
        ┌──────────────────────────────┐
        │ now = ticks_ms()             │
        └──────────────┬───────────────┘
                       ▼
        ┌──────────────────────────────┐   no
        │ need_advertise? ─────────────┼────────┐
        └──────────────┬───────────────┘        │
                       │ yes                    │
                       ▼                        │
        ┌──────────────────────────────┐        │
        │ advertise() (retry on error) │        │
        └──────────────┬───────────────┘        │
                       ▼                        ▼
        ┌──────────────────────────────┐
        │ queue non-empty & hold done? │
        └──────────────┬───────────────┘
             yes │            │ no
                 ▼            │
        ┌────────────────┐    │
        │ pop, render,   │    │
        │ notify ack     │    │
        └───────┬────────┘    │
                ▼             ▼
        ┌──────────────────────────────┐
        │ blink due? toggle active     │
        └──────────────┬───────────────┘
                       ▼
        ┌──────────────────────────────┐
        │ sleep 20 ms → loop           │
        └──────────────────────────────┘
```

---

## 8. End-to-end sequence (Nav session)

```
User        Nav app                 Valhalla        Device
 │ Connect    │                       │              │
 │───────────►│── GATT connect ──────────────────────►│
 │            │◄───────────────────── ack ready ──────│
 │ pick dest  │                       │              │
 │───────────►│                       │              │
 │ Go         │── POST /route ───────►│              │
 │───────────►│◄── shape+maneuvers ───│              │
 │            │ decode, draw route    │              │
 │            │── watchPosition ──┐   │              │
 │            │◄── GPS updates ───┘   │              │
 │            │ next turn → write ───────────────────►│ render
 │            │◄──────────────────── ack:<cmd> ──────│
 │            │ ... (distance updates, blink, arrive) │
 │ Stop       │── write "X" ─────────────────────────►│ idle
```

---

## 9. Configuration & tuning

| Constant | Where | Default | Meaning |
|---|---|---|---|
| `BLINK_M` | nav | 30 m | blink when this close to the turn |
| `ARRIVE_M` | nav | 30 m | send `A` this close to the destination |
| `BUCKET_M` | nav | 50 m | re-send distance every N metres |
| `COSTING` | nav | bicycle/pedestrian/auto | Valhalla profile per mode |
| `BLINK_MS` | firmware | 300 ms | blink half-period |
| `HOLD_MS` | firmware | 300 ms | min on-screen time per command |
| `BANNER_H` | firmware | 38 px | top banner height |
| `ARROW_X` | firmware | 53/160/267 | centres of the 3 arrow cells |
| `CACHE` | sw.js | `citinav-v3` | bump to force PWA update |

---

## 10. Failure modes & troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Connect` fails / no device | not a secure context | use the https tunnel or `localhost` |
| Device not found | already connected to another central (phone/Mac) | disconnect the other client |
| Device not advertising after a reset | ghost connection from soft reset | hard reset / power-cycle |
| `ack` never arrives | old firmware (pre-v2) | deploy `citinav_landscape.py` |
| Map blank | Leaflet CDN blocked / offline | check network; SW caches shell only |
| Search empty | Photon unreachable | retry; check network |
| Routing fails | Valhalla demo down / rate-limited | retry; consider a self-hosted Valhalla |
| Turns feel late/early | thresholds | tune `BLINK_M` / `BUCKET_M` |
| Stale app after update | service worker cache | bump `CACHE` in `sw.js` |

---

## 11. Privacy & security

- **No backend.** The apps are static files; routing/geocoding go directly from
  the phone to public services (Valhalla, Photon, OSM, Google).
- **Location** is used only in-browser for the nav loop; it is not stored or sent
  anywhere except as coordinates in the routing request.
- **BLE** is local and unauthenticated (prototype). Anyone in range could write
  commands; add pairing/bonding for production.
- **Tunnel** exposes the static page publicly while running; stop `cloudflared`
  when done. No secrets are served.
- **Google Maps handoff** opens a normal Maps URL; no data is read back.

---

## 12. File map

| Path | What |
|---|---|
| `webapp/index.html` | Nav app (Valhalla + GPS + auto-send) |
| `webapp/test.html` | Test app (map handoff + manual controls) |
| `webapp/manifest.json` | PWA manifest + shortcuts |
| `webapp/sw.js` | Service worker (offline shell) |
| `webapp/make_icons.py` | Icon generator |
| `webapp/serve.sh` | LAN host |
| `citinav_landscape.py` | Device firmware (BLE + LCD) |
| `citinav_send.py` | Terminal sender (same contract) |
| `deploy.sh` | Deploy firmware + reboot |
| `docs/CITINAV.md` | Product plan + BLE contract |
| `docs/CITINAV-MOBILEAPP-PLAN.md` | Native Android plan |
| `docs/GUI-DESIGN.md` | On-device UI / RAM budget |

---

## 13. Limitations & future work

- **Web Bluetooth is Android/desktop only** — no iOS.
- **Nav routing quality** depends on the public Valhalla demo (no SLA, rate
  limits, no live traffic). A self-hosted Valhalla/OSRM would fix this.
- **No off-route detection / reroute** yet — the loop assumes you follow the
  route; add cross-track distance checks and a re-route trigger.
- **Battery** — continuous high-accuracy GPS + screen-on is heavy; consider
  `watchPosition` throttling and wake-lock management.
- **No background operation** — a browser tab must stay active; a native app is
  required for true background navigation.
- **BLE security** — add bonding/authentication for production.
- **Test app** cannot mirror Google Maps notifications (browser limitation);
  that remains the native-app path.
