# ESP32-C6 + 1.47" LCD — Working Setup

**Verified:** 03 Nov 2026
**Board:** Waveshare **ESP32-C6-LCD-1.47** (172×320, sold under the "Wonrabai" brand on Amazon)
**Chip:** ESP32-C6FH8 (QFN32), 8 MB flash, Wi-Fi 6 + BT5(LE) + 802.15.4
**Firmware:** MicroPython v1.29.0 (ESP32_GENERIC_C6)

---

## 1. Display hardware

| Property | Value |
|---|---|
| Size | 1.47" IPS TFT |
| Resolution | 172 × 320 |
| Controller | ST7789 (172-wide panel inside 240-wide GRAM → **column offset 34**) |
| Interface | SPI (4-wire) |
| Colour depth | 16-bit RGB565 |
| Colour order | **BGR** |
| Display inversion | **INVON** (enabled) |

---

## 2. Pinout (onboard LCD, fixed)

| LCD pin | ESP32-C6 GPIO |
|---|---|
| MOSI (DIN) | **6** |
| SCLK | **7** |
| CS | **14** |
| DC | **15** |
| RST | **21** |
| BL (backlight) | **22** |
| RGB LED (extra) | 8 |
| SD card: MISO / CS | 5 / 4 |

SPI: `machine.SPI(1)` (FSPI/SPI2), **mode 0** (CPOL=0, CPHA=0), 40 MHz.

---

## 3. ST7789 init sequence (required — this is what makes it work)

The panel needs the full tuning sequence, **including `INVON`** (skipping these
causes wrong/blank/inverted colours):

```
0x11 SLPOUT      (120 ms delay)
0x13 NORON
0xB6 0x0A 0x82            Display Function Control
0x3A 0x55                 Interface format: 16-bit RGB565
0xB2 0x0C 0x0C 0x00 0x33 0x33   Porch control
0xB7 0x35                 Gate control
0xBB 0x28                 VCOMS
0xC0 0x0C                 Power control 1
0xC2 0x01 0xFF            Power control 2
0xC3 0x10                 Power control 3
0xC4 0x20                 Power control 4
0xC6 0x0F                 VCOM control 1
0xD0 0xA4 0xA1            Power control A
0xE0 0xD0 0x00 0x02 0x07 0x0A 0x28 0x32 0x44 0x42 0x06 0x0E 0x12 0x14 0x17   gamma (+)
0xE1 0xD0 0x00 0x02 0x07 0x0A 0x28 0x31 0x54 0x47 0x0E 0x1C 0x17 0x1B 0x1E   gamma (-)
0x21 INVON                display inversion ON
0x29 DISPON      (120 ms delay)
```

**MADCTL (0x36) = `0x08`** for portrait: BGR bit set, MX=MY=MV=0.
(That is: colour order BGR, no mirror, no axis swap.)

Rotation table for 172×320 (width, height, xstart, ystart, madctl base, swap):

| Rotation | madctl base | W×H | xstart | ystart |
|---|---|---|---|---|
| 0 (portrait) | 0x00 | 172×320 | 34 | 0 |
| 1 (landscape) | 0x60 | 320×172 | 0 | 34 |
| 2 (portrait 180°) | 0xC0 | 172×320 | 34 | 0 |
| 3 (landscape 180°) | 0xA0 | 320×172 | 0 | 34 |

> With `color_order=BGR`, the BGR bit (`0x08`) is OR-ed into the MADCTL value.

---

## 4. Working software

Uses the proven **`st7789py`** driver (devbis) + a VGA 8×16 font.

Files on the board:

```
boot.py        (stock)
main.py        (app)
st7789py.py    (LCD driver)
vga1_8x16.py   (font)
```

### main.py (minimal working example)

```python
from machine import Pin, SPI
import st7789py as st7789
import vga1_8x16 as font

C6_172x320_ROTATIONS = (
    (0x00, 172, 320, 34, 0, False),
    (0x60, 320, 172,  0, 34, False),
    (0xC0, 172, 320, 34, 0, False),
    (0xA0, 320, 172,  0, 34, False),
)

spi = SPI(1, baudrate=40_000_000, polarity=0, phase=0,
          sck=Pin(7), mosi=Pin(6))

tft = st7789.ST7789(spi, 172, 320,
                    reset=Pin(21, Pin.OUT),
                    dc=Pin(15, Pin.OUT),
                    cs=Pin(14, Pin.OUT),
                    backlight=Pin(22, Pin.OUT),
                    rotation=0,
                    color_order=st7789.BGR,
                    custom_rotations=C6_172x320_ROTATIONS)

tft.fill(st7789.BLACK)
tft.text(font, "Hello!", 10, 10, st7789.WHITE)
```

---

## 5. Daily workflow (CLI — no Web Serial needed)

> **Finding your serial port:** the device normally shows up as
> `/dev/cu.usbmodem101` (previously `…1101`). Run
> `~/.esptool-venv/bin/mpremote devs` and use the `/dev/cu.usbmodem*` entry that
> appears — the number changes with the USB port.

```bash
# Upload files
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem101 cp main.py :main.py

# Run without copying
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem101 run test.py

# Interactive REPL
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem101 repl

# List / read board files
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem101 ls
~/.esptool-venv/bin/mpremote connect /dev/cu.usbmodem101 cat main.py

# If REPL hangs after flashing, hard-reset into the app:
~/.esptool-venv/bin/esptool --chip esp32c6 --port /dev/cu.usbmodem101 --after hard-reset chip-id
```

---

## 6. Gotchas learned (keep for future reference)

1. **No serial port before flashing** — the ESP32-C6's native USB-Serial/JTAG
   reports a non-standard data-interface subclass (2) that macOS CDC drivers
   reject. After MicroPython boots it re-enumerates correctly and
   `/dev/cu.usbmodem*` appears.
2. **After flashing, the chip stays in the bootloader** → `mpremote` fails with
   "could not enter raw repl". Fix: hard-reset (esptool `--after hard-reset`,
   or press RST).
3. **A Chrome/Web-Serial tab holds the port** → "may be in use by another
   program". Fix: close the flasher/terminal tabs.
4. **Full init sequence is mandatory** — omitting the gamma/power/porch + `INVON`
   commands gives blank or scrambled colours.
5. **Byte order matters** — `framebuf` RGB565 is little-endian; this panel wants
   big-endian. The `st7789py` driver handles this internally (its `text`/`fill`
   encode big-endian). If you use `framebuf` directly, byte-swap each pixel.

---

## 7. Key paths

| Item | Value |
|---|---|
| Project dir | `/Users/zakaria/Documents/pi/ESP32/LCD147/` |
| Serial port | `/dev/cu.usbmodem101` (varies — check `mpremote devs`) |
| esptool / mpremote | `~/.esptool-venv/bin/` |
| Firmware | `ESP32_GENERIC_C6-20260824-v1.29.0.bin` |
| Full session log | `SETUP-REPORT.md` |