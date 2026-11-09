# CitiNav - Stage 1 (BLE peripheral, no routing)
# Phone writes direction commands to the command characteristic -> arrow on LCD.
#
#   L / R / S    -> static arrow  (left / right / straight)
#   LB / RB / SB -> SAME arrow but BLINKING
#   <dir>:<street> -> optional street text for the top banner
#                     e.g. "L:W 4th St", "RB:West 4th St"
#
# Uses the Nordic UART Service UUIDs from the CitiNav guide:
#   Service : 6e400001-b5a3-f393-e0a9-e50e24dcca9e
#   Command : 6e400002-b5a3-f393-e0a9-e50e24dcca9e   (WRITE / WRITE_NR)
#   Ack     : 6e400003-b5a3-f393-e0a9-e50e24dcca9e   (READ / NOTIFY)

import gc
import time
import machine
import bluetooth
from micropython import const
from machine import Pin, SPI
import st7789py as st7789
import vga1_8x16 as font
import vga2_bold_16x32 as bigfont

# ---- onboard LCD wiring (Waveshare ESP32-C6-LCD-1.47) ----
LCD_SCLK = 7
LCD_MOSI = 6
LCD_CS   = 14
LCD_DC   = 15
LCD_RST  = 21
LCD_BL   = 22

C6_172x320_ROTATIONS = (
    (0x00, 172, 320, 34, 0, False),
    (0x60, 320, 172,  0, 34, False),
    (0xc0, 172, 320, 34, 0, False),
    (0xa0, 320, 172,  0, 34, False),
)

BLE_NAME = "CitiNav"
BLINK_MS = 300            # blink half-period (ms)
HOLD_MS  = 300            # minimum time each command stays on screen
BANNER_H = 40             # top banner height (fits the 16x32 street font)
ARROW_Y0 = 42             # arrow area top (below banner)
ARROW_H  = 248            # arrow area height
LABEL_Y  = 294            # label baseline (near bottom, centred)

# ---- BLE constants ----
_IRQ_CENTRAL_CONNECT    = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE        = const(3)

_FLAG_READ              = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE             = const(0x0008)
_FLAG_NOTIFY            = const(0x0010)

_UUID_SVC = bluetooth.UUID("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
_UUID_CMD = bluetooth.UUID("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
_UUID_ST  = bluetooth.UUID("6e400003-b5a3-f393-e0a9-e50e24dcca9e")

_CHAR_CMD = (_UUID_CMD, _FLAG_READ | _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
_CHAR_ST  = (_UUID_ST,  _FLAG_READ | _FLAG_NOTIFY)
_SERVICE  = (_UUID_SVC, (_CHAR_CMD, _CHAR_ST))

LABELS = {"L": "TURN LEFT", "R": "TURN RIGHT", "S": "GO STRAIGHT"}

# street names shown in the top-middle banner.
# Populated over BLE (e.g. "L:W 4th St"), not hardcoded here.
STREETS = {}

BG     = st7789.color565(6, 28, 78)     # deep-blue page background
BANNER = st7789.color565(20, 70, 160)   # brighter blue top banner

# ---- globals ----
ble = None
tft = None
cmd_handle = None
st_handle = None
connections = set()
cmd_queue = []
cur_dir = None
cur_blink = False


# ================= drawing helpers =================

def fill_triangle(p0, p1, p2, color):
    """Scanline-filled triangle."""
    edges = ((p0, p1), (p1, p2), (p2, p0))
    ymin = min(p0[1], p1[1], p2[1])
    ymax = max(p0[1], p1[1], p2[1])
    for y in range(ymin, ymax + 1):
        nodes = []
        for (ax, ay), (bx, by) in edges:
            if ay == by:
                continue
            if (ay <= y < by) or (by <= y < ay):
                nodes.append(ax + (y - ay) * (bx - ax) / (by - ay))
        if nodes:
            xa = int(min(nodes))
            xb = int(max(nodes))
            if xb >= xa:
                tft.hline(xa, y, xb - xa + 1, color)


def arrow(cmd):
    cx, cy = 86, 150
    col = {"L": st7789.YELLOW, "R": st7789.CYAN, "S": st7789.GREEN}.get(cmd, st7789.WHITE)
    if cmd == "S":                                   # straight / up
        tft.fill_rect(cx - 18, cy - 10, 36, 120, col)
        fill_triangle((cx, cy - 90), (cx - 45, cy - 15), (cx + 45, cy - 15), col)
    elif cmd == "L":                                 # left
        tft.fill_rect(cx - 20, cy - 18, 80, 36, col)
        fill_triangle((cx - 80, cy), (cx - 15, cy - 45), (cx - 15, cy + 45), col)
    elif cmd == "R":                                 # right
        tft.fill_rect(cx - 60, cy - 18, 80, 36, col)
        fill_triangle((cx + 80, cy), (cx + 15, cy - 45), (cx + 15, cy + 45), col)


def draw_banner(blink, street):
    """Top banner with the large street name, horizontally centred."""
    tft.fill_rect(0, 0, 172, BANNER_H, BANNER)
    if street:
        x = (172 - len(street) * 16) // 2
        if x < 0:
            x = 0
        tft.text(bigfont, street, x, (BANNER_H - 32) // 2, st7789.WHITE)
    if blink:
        tft.fill_rect(162, 4, 6, 6, st7789.YELLOW)      # blink indicator


def draw_arrow(cmd, visible):
    """Clear just the arrow area and optionally redraw the arrow.
    The banner/label sit outside this area, so they never blink."""
    tft.fill_rect(0, ARROW_Y0, 172, ARROW_H, BG)
    if visible:
        arrow(cmd)


def draw_label(cmd):
    """Draw the label horizontally centred near the bottom (persistent)."""
    tft.fill_rect(0, LABEL_Y - 2, 172, 18, BG)
    label = LABELS.get(cmd)
    if label:
        x = (172 - len(label) * 8) // 2
        if x < 0:
            x = 0
        tft.text(font, label, x, LABEL_Y, st7789.WHITE)


def show_dir(cmd, blink):
    tft.fill(BG)
    draw_banner(blink, STREETS.get(cmd[:1], ""))
    draw_label(cmd)
    draw_arrow(cmd, True)


def show_idle():
    tft.fill(BG)
    tft.fill_rect(0, 0, 172, BANNER_H, BANNER)
    tft.text(font, "CitiNav", 6, (BANNER_H - 16) // 2, st7789.WHITE)
    tft.text(font, "Stage 1: BLE", 6, 50, st7789.GREEN)
    tft.text(font, "waiting for a", 6, 80, st7789.WHITE)
    tft.text(font, "command...", 6, 96, st7789.WHITE)
    tft.text(font, "L R S  = static", 6, 140, st7789.CYAN)
    tft.text(font, "LB RB SB = blink", 6, 160, st7789.YELLOW)
    tft.text(font, BLE_NAME, 6, 200, st7789.WHITE)


# ================= LCD =================

def lcd_setup():
    global tft
    spi = SPI(1, baudrate=40_000_000, polarity=0, phase=0,
              sck=Pin(LCD_SCLK), mosi=Pin(LCD_MOSI))
    tft = st7789.ST7789(spi, 172, 320,
                        reset=Pin(LCD_RST, Pin.OUT),
                        dc=Pin(LCD_DC, Pin.OUT),
                        cs=Pin(LCD_CS, Pin.OUT),
                        backlight=Pin(LCD_BL, Pin.OUT),
                        rotation=0,
                        color_order=st7789.BGR,
                        custom_rotations=C6_172x320_ROTATIONS)


# ================= BLE =================

def advertise():
    adv = bytearray([0x02, 0x01, 0x06])
    n = BLE_NAME.encode()
    adv += bytes([len(n) + 1, 0x09]) + n            # name in adv
    su = bytes(_UUID_SVC)
    resp = bytes([len(su) + 1, 0x07]) + su          # service UUID in scan resp
    ble.gap_advertise(100000, adv_data=adv, resp_data=resp)


def irq(event, data):
    if event == _IRQ_CENTRAL_CONNECT:
        connections.add(data[0])
        print("BLE: connected")
    elif event == _IRQ_CENTRAL_DISCONNECT:
        connections.discard(data[0])
        print("BLE: disconnected -> re-advertising")
        advertise()
    elif event == _IRQ_GATTS_WRITE:
        conn, attr = data
        if attr == cmd_handle:
            raw = ble.gatts_read(cmd_handle)
            try:
                txt = raw.decode().strip()
            except Exception:
                txt = ""
            if txt:
                parts = txt.split(":", 1)
                cmd = parts[0].strip().upper()
                street = parts[1].strip() if len(parts) > 1 else None
                if cmd[:2] in ("LB", "RB", "SB"):
                    cmd = cmd[:2]
                else:
                    cmd = cmd[:1]
                if cmd[:1] in ("L", "R", "S"):
                    cmd_queue.append((cmd, street))
                    print("BLE rx:", cmd, street or "")
                else:
                    print("unknown cmd:", cmd)


def ble_setup():
    global ble, cmd_handle, st_handle
    ble = bluetooth.BLE()
    ble.active(True)
    try:
        ble.config(gap_name=BLE_NAME)
    except Exception:
        pass
    try:
        ble.config(mtu=247)
    except Exception:
        pass
    ((cmd_handle, st_handle),) = ble.gatts_register_services((_SERVICE,))
    ble.gatts_write(st_handle, b"ready")
    ble.irq(irq)
    advertise()


# ================= main =================

def main():
    global cur_dir, cur_blink
    lcd_setup()
    show_idle()
    ble_setup()
    print("CitiNav ready: name=%s svc=%s cmd=%s" % (BLE_NAME, _UUID_SVC, _UUID_CMD))

    visible = True
    last_blink = time.ticks_ms()
    next_cmd_at = 0

    while True:
        now = time.ticks_ms()

        # take the next queued command (respecting the on-screen hold time)
        if cmd_queue and time.ticks_diff(now, next_cmd_at) >= 0:
            cmd, street = cmd_queue.pop(0)
            d = cmd[:1]
            if d in ("L", "R", "S"):
                cur_dir = d
                cur_blink = len(cmd) > 1 and cmd[1] == "B"
                if street is not None:
                    STREETS[d] = street[:10]
                show_dir(cur_dir, cur_blink)
                visible = True
                last_blink = now
                next_cmd_at = time.ticks_add(now, HOLD_MS)
                print("showing %s street=%r blink=%s"
                      % (cur_dir, STREETS.get(d, ""), cur_blink))
            else:
                print("unknown cmd:", cmd)

        # blink the current arrow
        if cur_blink and cur_dir:
            if time.ticks_diff(now, last_blink) >= BLINK_MS:
                visible = not visible
                last_blink = now
                draw_arrow(cur_dir, visible)

        time.sleep_ms(20)


if __name__ == "__main__":
    main()
