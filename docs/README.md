# CitiNav — Documentation Index

All project markdown lives here. Source code stays in the project root
(`../`).

| Doc | What it covers |
|---|---|
| [SETUP.md](SETUP.md) | **Setup guide**: flash the device, serve the app, expose it to the phone via a **Cloudflare Tunnel**, connect |
| [CITINAV.md](CITINAV.md) | Project plan: **Part 1 Devices** + **Part 2 Mobile app**, the shared **BLE contract**, and the simulators (terminal + Web Bluetooth) |
| [WEBAPP-TECHNICAL.md](WEBAPP-TECHNICAL.md) | **Technical reference** for the web apps: architecture, BLE contract, nav engine, firmware, data-flow & sequence diagrams |
| [WEBAPP-TECHNICAL.html](WEBAPP-TECHNICAL.html) | **Rendered HTML** of the technical reference — self-contained, with **all source code embedded** (rebuild: `python3 docs/build_html.py`) |
| [CITINAV-MOBILEAPP-PLAN.md](CITINAV-MOBILEAPP-PLAN.md) | Native **Android** app plan: Maps handoff, notification mirroring, BLE contract changes, roadmap |
| [GUI-DESIGN.md](GUI-DESIGN.md) | On-device **GUI design for small-memory** devices — RAM budgets, architecture options (framebuffer vs. not), low-RAM techniques |
| [LCD-SETUP.md](LCD-SETUP.md) | Hardware bring-up: pins, ST7789 init, driver, fonts, daily workflow |
| [SETUP-REPORT.md](SETUP-REPORT.md) | Session log: Mac performance fix + ESP32-C6 USB/BLE bring-up |

## Quick orientation

- **Setting it up (incl. the tunnel)?** → [SETUP.md](SETUP.md)
- **New to the project?** → [CITINAV.md](CITINAV.md) (start here)
- **How the web apps work?** → [WEBAPP-TECHNICAL.md](WEBAPP-TECHNICAL.md)
- **Building the UI?** → [GUI-DESIGN.md](GUI-DESIGN.md)
- **Wiring / LCD not working?** → [LCD-SETUP.md](LCD-SETUP.md)
- **Understanding tooling (esptool, mpremote, bleak)?** → [SETUP-REPORT.md](SETUP-REPORT.md)

## Source files (in `../`)

| File | Role |
|---|---|
| `citinav_landscape.py` | **active firmware (UI v2)**: landscape 3-arrow UI, green on dark grey |
| `citinav.py` | portrait firmware (v1) — fallback |
| `main.py` | boot launcher → runs `citinav_landscape.main()` |
| `citinav_send.py` | terminal command sender (arrows + street text) |
| `webapp/` | Web Bluetooth mobile simulator (`index.html`, `serve.sh`, `README.md`) |
| `deploy.sh` | deploy firmware to the board + reboot |
| `st7789py.py` | LCD driver |
| `vga1_8x16.py`, `vga2_bold_16x32.py` | fonts |
