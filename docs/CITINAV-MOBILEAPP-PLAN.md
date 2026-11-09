# CitiNav — Mobile App Plan (Part 2, Android)

*Revision of Part 2 of `CITINAV.md`. The app no longer computes routes. It hands the trip to Google Maps and mirrors Maps' turn-by-turn notifications to the CitiNav device over BLE.*

**Status:** Draft for review · a **Web Bluetooth quick-path** (Web app + Cloudflare tunnel) is already built and verified — see **§12**

---

## 1. Summary

The user picks a destination inside the CitiNav app and taps **Start**. The app launches Google Maps in navigation mode via a deep link. While Maps navigates, a background service in the CitiNav app reads Maps' ongoing navigation notification, extracts the turn direction, street name and distance, and writes a short command to the device over BLE.

```
 ┌─────────────────────┐   deep link    ┌───────────────┐
 │  CitiNav app        │ ─────────────► │  Google Maps  │
 │  - destination pick │                │  (navigating) │
 │  - trip lifecycle   │                └──────┬────────┘
 │                     │                       │ ongoing notification
 │  Foreground service │ ◄─────────────────────┘
 │  - NotificationListener (filter: Maps)
 │  - Parser  → command
 │  - BLE central (one connection per trip)
 └──────────┬──────────┘
            │  BLE write  "L:W 4th St:120"
            ▼
      CitiNav device (ESP32-C6 + LCD)
```

**Design principle (unchanged):** the device is a dumb display. The phone interprets, the device renders.

## 2. Scope and non-goals

**In scope**
- Android only
- Destination selection, Maps launch, notification mirroring, BLE sending, trip lifecycle
- Primary use case: bicycling

**Out of scope**
- Our own routing, rerouting, off-route detection and trigger-distance logic (Google handles all of it)
- iOS (no equivalent of notification access; revisit separately)
- Reading Maps' chosen route, ETA or arrival event beyond what the notification exposes

## 3. Components

| Component | Responsibility |
|---|---|
| **Destination picker** | Map + place search; produces lat/lng (and a display name) |
| **Launcher** | Builds the Maps deep link and starts it |
| **Foreground service** | Keeps the process alive while Maps is in the foreground; owns BLE and listener lifecycle |
| **NotificationListenerService** | Receives Maps notifications, filters to the navigation one |
| **Parser** | Notification fields → `{dir, street, dist_m}`; isolated and unit-tested |
| **BLE client** | Scans for `CitiNav`, keeps one connection per trip, writes commands, reads acks, reconnects |
| **Trip state machine** | idle → destination set → Maps launched → navigating → arrived / cancelled |

## 4. Maps handoff

**Preferred (Android intent):**
```
google.navigation:q=<lat>,<lng>&mode=b
```
- `mode`: `d` driving, `b` bicycling, `w` walking
- Set the package to `com.google.android.apps.maps` to avoid a chooser
- Optional `avoid=` flags exist for tolls, highways and ferries

**Fallback (https, if Maps is not installed or the intent fails):**
```
https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>&travelmode=bicycling&dir_action=navigate
```

Notes:
- Prefer coordinates over place names for reliability.
- Bicycling availability in Google Maps varies by region; verify for target markets.
- `dir_action=navigate` behavior has varied by version; test on target devices.
- Connect BLE **before** launching Maps so the first turn lands on an already-linked device.

## 5. Notification mirroring

### 5.1 Filtering
- Package: `com.google.android.apps.maps`
- Only the ongoing navigation notification (ignore other Maps notifications)
- Send on change only: dedupe against the last payload and throttle updates when only the distance ticks down
- On notification removed, send `X` and move the trip state to arrived/cancelled

### 5.2 Discovery step (do this first, before writing the parser)

Start navigation on a real phone and capture the notification:

```bash
adb shell dumpsys notification --noredact | grep -A40 "com.google.android.apps.maps"
```

Record: `android.title`, `android.text`, `android.subText`, large icon, and whether content is in custom `RemoteViews` instead of standard extras. If it is RemoteViews, the parser must walk the view tree. **Capture samples for each mode we care about (bicycling especially), several languages, and edge cases** (roundabouts, merge, keep left/right, U-turn, arrival).

> I have not verified the exact fields Maps populates. This step decides whether the whole approach is viable.

### 5.3 Parsing strategy

| Field | Source | Notes |
|---|---|---|
| Direction | Text ("Turn left onto...") with the arrow icon as fallback or cross-check | Text breaks per language and wording; icon is language-independent but needs a calibration table |
| Street | Text | ASCII-fold accents, strip `:`, truncate to 10 chars on the phone |
| Distance | Text ("200 ft", "0.3 mi", "450 m") | Parse units, convert to meters |

Requirements:
- Parser is a pure function with no Android dependencies, so it can be tested on a desktop.
- Log every unparseable notification (without personal data beyond what is needed) so format drift is easy to spot.
- Unknown direction → send `S` with the street, or skip; decide and document.

## 6. BLE contract changes

Extends §5 of `CITINAV.md`. Both sides build to this.

### 6.1 Command grammar

```
<dir>[B][:<street>[:<dist_m>]]
```

| `dir` | Meaning | Device shows |
|---|---|---|
| `L` | Turn left | Left arrow |
| `R` | Turn right | Right arrow |
| `S` | Straight / continue | Straight arrow |
| `U` | U-turn | U-turn arrow (**new**) |
| `A` | Arrive | Destination/flag screen (**new**) |
| `X` | Clear / idle | Blank or idle screen (**new**) |

- `B` suffix (after `L`, `R`, `S`, `U`) = blink
- `street`: ASCII only, max 10 chars, truncated by the **app**
- `dist_m`: integer meters to the maneuver
- Examples: `L`, `LB`, `R:Broadway`, `LB:W 4th St:30`, `A`, `X`
- Keep the total ≤ 20 bytes so no MTU negotiation is needed
- Case-insensitive; unknown first char is ignored and logged on the device

### 6.2 Device behavior to add (firmware side)
- Latest-wins handling instead of queueing every command (keep a short minimum on-screen hold only)
- Optional auto-blink when `dist_m` falls under a threshold (e.g. 30 m)
- Stale-link state: if no command or ping arrives for a timeout, show "no signal" instead of the last arrow
- Show distance when provided

### 6.3 Ack
- Keep `ack:<cmd>`; consider a sequence number if reliable latency measurement is needed (open item)

### 6.4 Other contract items
- Unique advertised name suffix per unit (e.g. `CitiNav-A3F2`)
- Protocol version readable from the device
- Single connection reused for the whole trip; define reconnect behavior (retry with backoff, resend the latest state on reconnect)

## 7. Trip lifecycle

| State | Trigger | Device command | App action |
|---|---|---|---|
| Idle | App open, no trip | `X` | — |
| Destination set | User picks a place | — | Show route summary / Start button |
| Connecting | User taps Start | — | Scan and connect BLE |
| Maps launched | BLE connected | `X` | Launch Maps deep link; start a "no notification" watchdog |
| Navigating | Navigation notification updates | `L`/`R`/`S`/`U` + street + dist | Parse, dedupe, send |
| Arrived | "Arrive" text or notification removed after near-destination | `A`, then `X` | Optionally bring the app to the foreground |
| Cancelled / Maps killed | Notification removed early | `X` | Reset state |
| Watchdog fired | No Maps notification within N seconds of launch | `X` | Show "Navigation didn't start" in the app |
| BLE lost | Disconnect | (device shows "no signal" after timeout) | Reconnect with backoff, resend latest state |

## 8. Android requirements and limits

- **Notification Access** must be granted by the user in system settings (not a runtime permission): needs an onboarding screen that explains why.
- **Bluetooth permissions** (`BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT` on Android 12+) and location as required for scanning on older versions.
- **Foreground service** holding BLE and the listener lifecycle; request exemption from battery optimization or Android will kill it mid-ride. Check OEM-specific background restrictions on target phones.
- Android may unbind the listener; call `requestRebind` and handle it.
- **Fragility:** a Maps update can change the notification format. Keep the parser isolated, versioned and covered by sample-based tests.
- **Terms of service:** mirroring another app's notifications is outside any official API. Confirm it is acceptable for the intended distribution (personal/prototype vs published app) before going beyond a prototype.
- The user can change the route inside Maps; the app will not know, and that is fine because it mirrors whatever Maps does.

## 9. Testing

1. **Manual BLE check:** nRF Connect or LightBlue writing `L`, `RB`, `LB:W 4th St:30` to the Command characteristic.
2. **Parser tests:** a library of captured notification dumps (title, text, subText, icon hash) with expected commands, run on a desktop.
3. **Notification replay tool:** feeds saved dumps through the parser and prints commands (optionally sends them over BLE). This replaces the planned `citinav_nav_sim.py` for Part 2 validation.
4. **Field test:** real bike ride with Maps; log notification → parse → write → ack timestamps.
5. **Failure drills:** disable Bluetooth mid-trip, kill Maps, kill the app, lose GPS, switch language.

**Targets (proposed, to be agreed):**
- Notification received → device updated: p95 < 500 ms
- Write → ack: p95 < 200 ms
- Zero stale arrows after navigation ends

## 10. Roadmap

**Stage 2A0 — Web app quick win (fast path to a phone BLE client)** ✅ built
- [x] Web Bluetooth page (`webapp/index.html`) matching the §6 grammar (subset)
- [x] LAN host (`webapp/serve.sh`) + **Cloudflare quick tunnel** for a secure origin
- [x] Verified end-to-end from **Android Chrome** (see §12)
- [ ] Stable origin (named tunnel or mkcert) instead of a rotating URL
- [ ] PWA install + offline load
- [ ] Full §6 command parity (`U`/`A`/`X`, `dist_m`)

**Stage 2A — De-risk**
- [ ] Capture Maps notification samples on a real phone (bicycling, several languages)
- [ ] Decide icon vs text for direction
- [ ] Finalize the §6 contract with the firmware side

**Stage 2B — Build**
- [ ] Parser + unit tests from captured samples
- [ ] Notification listener + foreground service
- [ ] BLE client (connect once, reconnect, ack logging)
- [ ] Destination picker + Maps launcher
- [ ] Trip state machine and watchdogs

**Stage 2C — Device updates (firmware side)**
- [ ] New grammar, `U`/`A`/`X`, distance display
- [ ] Latest-wins command handling
- [ ] Stale-link "no signal" state
- [ ] Unique name suffix and protocol version

**Stage 3 — Integration**
- [ ] End-to-end field test and latency measurement
- [ ] Reliability fixes (battery, background, reconnect)

## 11. Open questions

1. Is the navigation notification standard extras or custom `RemoteViews`? (Decided by the discovery step.)
2. Which place-search and map stack? (Google Places/Maps SDK, Mapbox, or OSM with Nominatim and MapLibre; mind usage policies and costs.)
3. How is the arrow icon matched, if used? (Hash table vs bitmap comparison.)
4. Do we need a sequence number in ack for latency measurement?
5. Is a later iOS version expected? If so, it needs a different approach (own routing or a navigation SDK).
6. Distribution: personal prototype or public release? (Affects the ToS question in §8.)
7. Web app (§12): named tunnel with a real domain vs. quick tunnel vs. `mkcert` local CA?
8. Web app (§12): can a cached PWA stay a *secure context* for Web Bluetooth with no tunnel after first load?

---

## 12. Web app delivery — Web Bluetooth over a Cloudflare tunnel (fast path)

*The sections above target a native Android app. In parallel, `webapp/` (already
built and verified) is a working phone BLE client **today** — no Android SDK, no
Flutter, no Play distribution, no NotificationListener plumbing. This section
plans how to harden and extend it.*

### 12.1 Why a tunnel (the secure-context problem)

Web Bluetooth only runs in a **secure context**. A page served from the Mac at
`http://<mac-ip>:8000` is *not* secure, so Chrome on Android blocks
`navigator.bluetooth` (only the phone's own `localhost` is exempt, which is not
the Mac). An `https://` origin is required.

A **Cloudflare quick tunnel** provides a free, temporary
`https://…trycloudflare.com` origin that proxies to the Mac's local server — no
account, no domain, no certificate to install on the phone. It is the method
verified working.

```
 Mac (host)                                     Android phone (Chrome)
 ┌────────────────────────────┐                 ┌───────────────────────────┐
 │ python -m http.server 8000 │   https proxy   │ https://…trycloudflare.com │
 │   → webapp/index.html      │ ◄─────────────► │  • loads page (secure)     │
 │ cloudflared tunnel --url   │                 │  • Web Bluetooth → CitiNav │
 │   http://localhost:8000    │                 │    (BLE is phone-local)    │
 └────────────────────────────┘                 └───────────────────────────┘
```

**Key point:** the tunnel is only needed to **deliver** the page. Once loaded,
BLE traffic is phone ↔ device and never leaves the phone, so the ride-time path
has no internet dependency and no added latency.

### 12.2 Current state (prototypes built)

| Piece | What |
|---|---|
| `webapp/index.html` — **Nav (v4)** | **self-routing** navigation: **Valhalla** (bicycle/pedestrian/auto) + `watchPosition` → auto-sends `L/R/S/U/A` (street + distance, blink near turns) to the device. **No Google Maps, no notification access.** |
| `webapp/test.html` — **Test (v3)** | map picker (Leaflet/OSM, Photon) + **Start in Google Maps** handoff, plus **manual** BLE controls (`L/S/R/U/A/X`, blink, street, distance, ack log) |
| `webapp/manifest.json` + `sw.js` + `icon-*.png` | installable **PWA** (offline app shell); icons generated by `make_icons.py` |
| `webapp/serve.sh` | binds `0.0.0.0:8000`, prints the Mac + phone URLs and secure-context options |
| Tunnel | `cloudflared tunnel --url http://localhost:8000` (also `npx ngrok http 8000`) |
| Firmware | `citinav_landscape.py` parses the full §6 grammar (`U`/`A`/`X`, `dist_m`) — code ready, **deploy pending** |
| Verified | Android Chrome → quick-tunnel https URL → connect → `L/S/R` commands → acks |

### 12.3 Milestones

- [x] **PWA.** `manifest.json` + `sw.js` + generated icons → installable, offline shell.
- [x] **Destination picker + Maps handoff (§3–§4).** Map search + pin + travel mode → `google.com/maps/dir` deep link (web prototype of the native picker).
- [x] **Web navigation (self-routing).** Valhalla route + GPS → auto-sends turns; **removes the Maps-notification dependency** for the web path.
- [x] **Command parity (§6).** UI sends `U`/`A`/`X` and `dist_m`; firmware parses them.
- [x] **UX.** Remember last street/distance/Blink (`localStorage`); live payload
      preview; vibration on send; keyboard shortcuts.
- [x] **Reconnect.** Auto-reconnect with exponential backoff.
- [ ] **Stable origin.** Replace the rotating quick-tunnel URL with a **named
      Cloudflare tunnel + a real (sub)domain** so the URL is constant and can be
      bookmarked/installed. (Alternative for offline: a local `mkcert` CA + https.)
- [ ] **Device handling.** Device picker by name suffix (`CitiNav-A3F2`); read a
      protocol/version value; show stale-link state.
- [ ] **Deploy + verify firmware** on the device (`./deploy.sh`) — board was offline
      when this prototype was built.
- [ ] **Optional.** A “trip” preset (sequence of turns) to replay a route for demos.

### 12.4 Limitations & risks

| Risk | Impact | Mitigation |
|---|---|---|
| **iOS has no Web Bluetooth** | iPhone unusable | Native app only (§1–§11); document clearly |
| Quick-tunnel URL changes each run | can't bookmark / install | named tunnel + domain (§12.3), or mkcert |
| Needs the Mac powered + online to *load* | no startup if Mac is off | PWA offline caching; or host the static page on any https host |
| Cloudflare quick tunnels: no SLA, occasional blocks | flaky delivery | named tunnel, or `ngrok`, or mkcert |
| Chrome-only | no Firefox/Safari | acceptable for a simulator; note it |
| **Not the real Part 2 app** | no Maps mirroring, no routing | it's a manual test client; keep §1–§11 as the product plan |

### 12.5 Relationship to the native app

The web app is a **test harness**, not a replacement: it drives the device by
hand (same role as `citinav_send.py`, but touchable and phone-side). The native
Android app remains the product because it alone can mirror Maps notifications.
The two share the **§6 BLE contract**, so the device firmware work
(`U`/`A`/`X`, `dist_m`, latest-wins, stale-link) benefits both.

The **Test app (v3)** prototypes §3 (destination picker) and §4 (Maps handoff).
The **Nav app (v4)** goes further: it computes its **own** route and drives the
device from GPS — so it needs neither Maps nor the §5 notification mirroring. It
is the closest web equivalent of the product, at the cost of routing quality
(public Valhalla demo) and battery, and it can't share Google's live traffic.
The native Android app remains the product for the Maps-notification approach.
