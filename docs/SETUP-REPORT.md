# ESP32-C6 (LCD147) — Setup & Diagnosis Report

**Date:** 03 Nov 2026
**Machine:** Apple Silicon Mac (Apple T8122 / M4-class), macOS with DriverKit
**Project dir:** `/Users/zakaria/Documents/pi/ESP32/LCD147/`

---

## 1. Session summary

| Task | Result |
|---|---|
| Diagnose slow Mac | ✅ Root cause found (RAM starvation + Docker VM) |
| Stop Docker | ✅ Stopped (containers, VM, and all processes) |
| Diagnose ESP32-C6 USB | ✅ Root cause found (macOS CDC driver mismatch) |
| Install esptool | ✅ v5.6.0 in `~/.esptool-venv` |
| Download MicroPython firmware | ✅ v1.29.0 (validated) |
| Flash MicroPython (Web Serial) | ✅ Done (user confirmed) |
| Serial port available | ✅ `/dev/cu.usbmodem1101` appeared after flash |

---

## 2. Mac performance diagnosis (resolved)

**Symptom:** Sluggish system.

**Root cause:** Memory starvation on an **8 GB** machine:
- Docker VM allocated **3.8 GB** (47% of RAM), running 2 containers
  (`nyu-project` devcontainer + `postgres:15-alpine`)
- Swap was **86% full** (7 GB of 8 GB)
- Free memory: **14%**
- Load average: **20–50** (extremely high)
- 17 days of uptime → accumulated processes
- `WallpaperAerialsExtension` (animated aerial wallpaper) burning **42% CPU**

**Actions taken:**
- ✅ Stopped and removed Docker containers: `nyu-project`, `products_devcontainer-postgres-1`
- ✅ Quit Docker Desktop and killed lingering backend processes (3.8 GB freed)

**Recommended (not yet done):**
- [ ] Switch to a **static wallpaper** (System Settings → Wallpaper) — saves 42% CPU
- [ ] Reboot once to clear 17 days of process state and reset swap
- [ ] Optionally lower Docker's memory limit (Settings → Resources → ~2 GB)
  if you need to keep it running

---

## 3. ESP32-C6 USB connection diagnosis

**Device:** ESP32-C6 (native **USB-Serial/JTAG**, not a CP210x/CH340 bridge)
- Vendor `0x303A` (Espressif), Product `0x1001` ("USB JTAG/serial debug unit")
- Serial: `14:C1:9F:04:06:5C`

**Problem:** Board detected at USB level, but **no `/dev/cu.usbmodem*` port** existed,
so `esptool`/Arduino/serial monitors could not see it.

**Root cause (confirmed):**

The ESP32-C6's USB-Serial/JTAG exposes 3 interfaces:

| Interface | Class | Role | Driver |
|---|---|---|---|
| 0 | CDC Communications (ACM) | Control | ✅ `AppleUSBACMControl` |
| 1 | **CDC Data ("USB UART")** | **Serial** | ❌ **no driver** |
| 2 | Vendor-specific | JTAG | — |

Its **data interface (interface 1) reports `bInterfaceSubClass = 2`** (non-standard;
a normal CDC data interface is `0`). macOS CDC-ACM data drivers require subclass `0`:

- Apple `AppleUSBCDC` kext → requires subclass 0 → **no match**
- Samsung Smart Switch DEXT (`SamsungACMData`) → requires subclass 0 → **no match**

Therefore **no driver ever attached to the data interface → no serial port.**

**Red herring ruled out:** the Samsung Smart Switch DriverKit extensions
(`SamsungACMData/ACMControl/MTP/Serial/Composite`) are installed but were *not*
the cause (they can't match the C6's subclass-2 data interface). Still worth
uninstalling if you never use Samsung Galaxy USB devices:
`/Applications/Smart Switch/Uninstall.app`.

---

## 4. MicroPython setup (completed)

**Tools installed:**
```
~/.esptool-venv/bin/esptool       # v5.6.0
~/.esptool-venv/bin/mpremote      # official MicroPython CLI tool
```

**Firmware downloaded & validated:**
```
File:    ESP32_GENERIC_C6-20260824-v1.29.0.bin
Version: v1.29.0 (latest stable)
Size:    1,967,664 bytes
SHA256:  3688ba4e2c3949e639f5772e99fdb0efa1258b162a496133f78c108434195c89
Valid:   ✔ esptool image_info → ESP32-C6 (Chip ID 13), checksum & hash OK
```

**Flashing method:** Web Serial via browser (no serial port existed at the time).
- esp.huhn.me (ESP Web Flasher) — firmware at offset `0x0`
- Required holding the **BOOT** button to enter download mode
  (native USB has no DTR/RTS auto-reset)

---

## 5. Current state — VERIFIED WORKING

After flashing, the C6 rebooted into MicroPython and **re-enumerated with a proper
CDC descriptor**, so macOS finally created a serial port:

```
/dev/cu.usbmodem1101
```

**This means Web Serial is no longer needed for day-to-day work.** You can now use
standard CLI tools directly.

### ✅ Live verification (03 Nov 2026)

```
PLATFORM: esp32
VER:      3.4.0; MicroPython v1.29.0 on 2026-08-24
FREQ:     160000000    (160 MHz)
MEM_FREE: 331040 bytes
```

```
Chip:     ESP32-C6FH8 (QFN32), revision v0.2
Features: Wi-Fi 6, BT 5 (LE), IEEE802.15.4, single core + LP core, 160 MHz
Flash:    8 MB embedded
Crystal:  40 MHz
MAC:      14:c1:9f:04:06:5c
```

### Two gotchas encountered (and their fixes)

1. **"may be in use by another program"** — a Chrome tab (the flasher/terminal)
   holds the USB port exclusively. Fix: close those tabs (or click Disconnect).
2. **"could not enter raw repl"** — after flashing, the chip sits in the ROM
   bootloader. Fix: hard-reset it:
   ```bash
   ~/.esptool-venv/bin/esptool --chip esp32c6 --port /dev/cu.usbmodem1101 --after hard-reset chip-id
   ```
   (or simply press the board's **RST/EN** button once)

---

## 6. Daily workflow (CLI)

```bash
# Verify MicroPython is alive
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem1101 exec "import sys,os,machine,gc; print(sys.platform); print(sys.version); print(machine.freq()); print(os.uname().machine)"

# Open interactive REPL
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem1101 repl

# Upload code
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem1101 cp main.py :main.py

# Run a file
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem1101 run main.py

# List files on the board
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem1101 ls

# esptool is also ready now (flash, erase, chip info)
~/.esptool-venv/bin/esptool --chip esp32c6 --port /dev/cu.usbmodem1101 chip-id
```

---

## 7. Next steps for LCD147

1. Close the browser flasher/terminal tabs to release `/dev/cu.usbmodem1101`.
2. Run the verification command above (confirm `sys.platform == 'esp32'`).
3. Tell the assistant what the LCD147 hardware is:
   - Display controller (e.g. ST7789 / ILI9341 / GC9A01 / SSD1306)
   - Interface (SPI / I2C / 8-bit parallel)
   - What should be displayed
4. The assistant can then write `main.py` and upload it via `mpremote`.

---

## 8. Deployment log

`main.py` written, uploaded, and verified running on boot (03 Nov 2026):

```bash
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem1101 cp main.py :main.py
```

Boot output confirms: MicroPython 3.4.0 / v1.29.0, 160 MHz, ~328 KB free RAM,
6 MB LittleFS filesystem. **I2C scan found no devices** on common pin pairs
(6,7), (7,6), (18,19), (4,5), (21,22), (8,9) — so the LCD147 is likely SPI/parallel
(or I2C on a pin pair not yet tried).

---

## 9. Update — 04 Nov 2026: street text over BLE + firmware

The device no longer hardcodes mock street names. Street text is now sent from
the Mac over BLE using `dir:street` commands (Option A in `CITINAV.md` §5.5).

- Updated `citinav.py` (device) and `citinav_send.py` (sender).
- Flashed `citinav.py` (9,507 bytes) to the board on **`/dev/cu.usbmodem101`**
  (the port number changed from `…1101` — check `mpremote devs`).
- Hard-reset the board; it boots `main.py` and advertises **`CitiNav`**.
- Smoke test over BLE wrote `L:W 4th St`, `RB:Broadway`, `S:5th Ave`; the
  connection stayed up and the board processed all three without error.

Example usage (from the project root):

```bash
./citinav_send.py "L:W 4th St" "RB:Broadway"
```

---

## Appendix — key paths & commands

| Item | Value |
|---|---|
| Project dir | `/Users/zakaria/Documents/pi/ESP32/LCD147/` |
| Firmware file | `ESP32_GENERIC_C6-20260824-v1.29.0.bin` |
| esptool | `~/.esptool-venv/bin/esptool` (v5.6.0) |
| mpremote | `~/.esptool-venv/bin/mpremote` |
| Serial port | `/dev/cu.usbmodem101` (04 Nov; varies — check `mpremote devs`) |
| Chip | ESP32-C6FH8 (QFN32) rev v0.2, 8 MB flash, Wi-Fi 6 + BT5(LE) + 802.15.4 |