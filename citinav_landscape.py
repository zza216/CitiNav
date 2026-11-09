# CitiNav - Stage 1b / UI v2 (LANDSCAPE, 3-arrow UI)
#
# v2: this file is the boot app (main.py imports it). Same BLE contract as
#     citinav.py; only the on-screen layout differs (three horizontal arrows).
#
# Same BLE contract as citinav.py (Nordic UART UUIDs, same commands): only the
# on-screen layout changes. The LCD is rotated to landscape (320x172) and shows
# THREE arrows in a horizontal row - left | straight | right. The commanded
# direction is drawn bright + boxed; the other two stay dimmed. Blinking still
# blinks the commanded arrow.
#
#   L / R / S    -> highlight that arrow (static)
#   LB / RB / SB -> highlight that arrow but BLINKING
#   <dir>:<street> -> also shows the street text in the top banner
#
#   Service : 6e400001-b5a3-f393-e0a9-e50e24dcca9e
#   Command : 6e400002-b5a3-f393-e0a9-e50e24dcca9e   (WRITE / WRITE_NR)
#   Ack     : 6e400003-b5a3-f393-e0a9-e50e24dcca9e   (READ / NOTIFY)

import gc
import math
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

# rotation 1 == landscape (320x172); see docs/LCD-SETUP.md
C6_172x320_ROTATIONS = (
    (0x00, 172, 320, 34, 0, False),
    (0x60, 320, 172,  0, 34, False),
    (0xc0, 172, 320, 34, 0, False),
    (0xa0, 320, 172,  0, 34, False),
)

# ---- landscape geometry (screen is 320 wide x 172 tall) ----
W, H = 320, 172

VERSION  = 2              # UI version (see docs/CITINAV.md)
BLE_NAME = "CitiNav"
BLINK_MS = 300            # blink half-period (ms)
HOLD_MS  = 300            # minimum time each command stays on screen
BANNER_H = 38             # top banner height (fits the 16x32 street font)
ARROW_Y0 = BANNER_H       # arrows area top
LABEL_Y  = H - 18         # bottom label baseline
ARROW_H  = LABEL_Y - ARROW_Y0   # arrows area height
ARROW_CY = ARROW_Y0 + ARROW_H // 2
ARROW_X = (53, 160, 267)  # centres of the three horizontal cells
CELL_HW = 50              # half-width of the active-cell box

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

LABELS = {"L": "TURN LEFT", "R": "TURN RIGHT", "S": "GO STRAIGHT",
          "U": "U-TURN", "A": "ARRIVED"}

# street names shown in the top banner; populated over BLE, not hardcoded here.
STREETS = {}

BG     = st7789.color565(32, 32, 32)     # dark-grey page background
BANNER = st7789.color565(58, 58, 58)     # lighter grey top banner
ARROW  = st7789.color565(0, 220, 80)     # green arrows
DIM    = st7789.color565(28, 66, 40)     # inactive (dimmed) arrows
COLORS = {"L": ARROW, "R": ARROW, "S": ARROW, "U": ARROW, "A": ARROW}

# ---- globals ----
ble = None
tft = None
cmd_handle = None
st_handle = None
connections = set()
cmd_queue = []
cur_dir = None
cur_blink = False
cur_dist = None
need_advertise = False      # set by the BLE IRQ, handled in the main loop
adv_retry_at = 0


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


def arrow(cmd, cx, cy, col, k=2):
    """Draw a single L/R/S arrow centred at (cx, cy).

    k is the downscale divisor: k=2 draws the arrow at half the size used by
    the portrait firmware, so three of them fit across the landscape screen.
    """
    if cmd == "S":                                   # straight / up
        hw = 45 // k
        shw = 18 // k
        top = cy - 90 // k
        neck = cy - 15 // k
        bot = cy + 110 // k
        tft.fill_rect(cx - shw, neck, shw * 2, bot - neck, col)
        fill_triangle((cx, top), (cx - hw, neck), (cx + hw, neck), col)
    elif cmd == "L":                                 # left
        w = 80 // k
        h = 45 // k
        sh = 18 // k
        tft.fill_rect(cx - 20 // k, cy - sh, w, sh * 2, col)
        fill_triangle((cx - w, cy), (cx - 15 // k, cy - h),
                      (cx - 15 // k, cy + h), col)
    elif cmd == "R":                                 # right
        w = 80 // k
        h = 45 // k
        sh = 18 // k
        tft.fill_rect(cx - 60 // k, cy - sh, w, sh * 2, col)
        fill_triangle((cx + w, cy), (cx + 15 // k, cy - h),
                      (cx + 15 // k, cy + h), col)


def arrow_uturn(cx, cy, col):
    """A left U-turn glyph centred at (cx, cy) — fits inside the arrow area."""
    w = 24
    left = cx - 50
    right = cx + 50 - w
    top = cy - 56
    bottom = cy + 22
    tft.fill_rect(left, top, w, bottom - top, col)               # left upright
    tft.fill_rect(right, top, w, bottom - top, col)              # right upright
    tft.fill_rect(left, top, (right + w) - left, w, col)         # top bar
    fill_triangle((left + w // 2, bottom + 30),
                  (left - 15, bottom), (left + w + 15, bottom), col)


def ring(cx, cy, r, t, color):
    """Draw a ring (wheel) of thickness t using horizontal spans."""
    for dy in range(-r, r + 1):
        dx = int(math.sqrt(max(0, r * r - dy * dy)))
        tft.hline(cx - dx, cy + dy, t, color)
        tft.hline(cx + dx - t + 1, cy + dy, t, color)


def draw_bicycle(cx, cy, color):
    """A simple side-view bicycle centred on the wheel-axle line."""
    r = 20
    lw = (cx - 58, cy)          # rear wheel
    fw = (cx + 58, cy)          # front wheel
    bb = (cx - 6, cy + 6)       # bottom bracket
    seat = (cx - 34, cy - 30)   # seat top
    bar = (cx + 38, cy - 34)    # handlebar
    ring(lw[0], lw[1], r, 3, color)
    ring(fw[0], fw[1], r, 3, color)
    # frame
    tft.line(lw[0], lw[1], bb[0], bb[1], color)       # chainstay
    tft.line(bb[0], bb[1], seat[0], seat[1], color)   # seat tube
    tft.line(seat[0], seat[1], lw[0], lw[1], color)   # seat stay
    tft.line(seat[0], seat[1], bar[0], bar[1], color) # top tube
    tft.line(bb[0], bb[1], bar[0], bar[1], color)     # down tube
    tft.line(bar[0], bar[1], fw[0], fw[1], color)     # fork
    # seat + handlebar
    tft.hline(seat[0] - 9, seat[1], 18, color)
    tft.hline(bar[0] - 9, bar[1], 18, color)
    # crank
    ring(bb[0], bb[1], 5, 2, color)


def draw_banner(blink, street):
    """Top banner with the large street name, horizontally centred."""
    tft.fill_rect(0, 0, W, BANNER_H, BANNER)
    if street:
        x = (W - len(street) * 16) // 2
        if x < 0:
            x = 0
        tft.text(bigfont, street, x, (BANNER_H - 32) // 2, st7789.WHITE, BANNER)
    if blink:
        tft.fill_rect(W - 10, 4, 6, 6, st7789.YELLOW)   # blink indicator


def draw_arrows(active, visible):
    """Redraw the whole horizontal arrow row.

    All three arrows are always shown; the commanded one is highlighted with
    its colour plus a box, the others are dimmed. When blinking, `visible`
    toggles whether the active arrow itself is painted (its box stays).
    """
    tft.fill_rect(0, ARROW_Y0, W, ARROW_H, BG)
    for cmd, cx in zip(("L", "S", "R"), ARROW_X):
        if cmd == active:
            tft.rect(cx - CELL_HW, ARROW_Y0 + 3, CELL_HW * 2, ARROW_H - 8,
                     COLORS.get(cmd, st7789.WHITE))
            if visible:
                arrow(cmd, cx, ARROW_CY, COLORS.get(cmd, st7789.WHITE))
        else:
            arrow(cmd, cx, ARROW_CY, DIM)


def draw_label(cmd, dist=None):
    """Draw the label (and distance) centred at the bottom (persistent)."""
    tft.fill_rect(0, LABEL_Y - 2, W, 18, BG)
    label = LABELS.get(cmd)
    if label:
        if dist:
            label = "%s  %sm" % (label, dist)
        x = (W - len(label) * 8) // 2
        if x < 0:
            x = 0
        tft.text(font, label, x, LABEL_Y, COLORS.get(cmd, st7789.WHITE), BG)


def show_dir(cmd, blink):
    tft.fill(BG)
    draw_banner(blink, STREETS.get(cmd[:1], ""))
    draw_label(cmd, cur_dist)
    draw_arrows(cmd, True)


def show_uturn(blink):
    tft.fill(BG)
    draw_banner(blink, STREETS.get("U", ""))
    draw_label("U", cur_dist)
    tft.fill_rect(0, ARROW_Y0, W, ARROW_H, BG)
    arrow_uturn(W // 2, ARROW_CY, ARROW)


def show_arrive():
    tft.fill(BG)
    draw_banner(False, STREETS.get("A", ""))
    msg = "ARRIVED"
    tft.text(bigfont, msg, (W - len(msg) * 16) // 2, ARROW_CY - 16, ARROW, BG)


def show_idle():
    """Boot / waiting screen: 'CitiNav' in yellow with a bicycle below."""
    tft.fill(BG)                                        # whole screen dark grey
    title = "CitiNav"
    tft.text(bigfont, title, (W - len(title) * 16) // 2, 24, st7789.YELLOW, BG)
    draw_bicycle(W // 2, 116, ARROW)


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
                        rotation=1,          # <- landscape
                        color_order=st7789.BGR,
                        custom_rotations=C6_172x320_ROTATIONS)


# ================= BLE =================

def advertise():
    adv = bytearray([0x02, 0x01, 0x06])
    n = BLE_NAME.encode()
    adv += bytes([len(n) + 1, 0x09]) + n            # name in adv
    su = bytes(_UUID_SVC)
    resp = bytes([len(su) + 1, 0x07]) + su          # service UUID in scan resp
    try:
        ble.gap_advertise(None)                     # stop any stale advertising
    except Exception:
        pass
    ble.gap_advertise(100000, adv_data=adv, resp_data=resp)


def irq(event, data):
    if event == _IRQ_CENTRAL_CONNECT:
        connections.add(data[0])
        print("BLE: connected")
    elif event == _IRQ_CENTRAL_DISCONNECT:
        connections.discard(data[0])
        print("BLE: disconnected -> will re-advertise")
        # Do NOT call advertise() from the IRQ: gap_advertise can raise
        # OSError(-30) in interrupt context and wedge the stack. Defer it.
        global need_advertise
        need_advertise = True
    elif event == _IRQ_GATTS_WRITE:
        conn, attr = data
        if attr == cmd_handle:
            raw = ble.gatts_read(cmd_handle)
            try:
                txt = raw.decode().strip()
            except Exception:
                txt = ""
            if txt:
                parts = txt.split(":", 2)
                head = parts[0].strip().upper()
                street = parts[1].strip() if len(parts) > 1 else None
                dist = parts[2].strip() if len(parts) > 2 else None
                d = head[:1]
                if d in ("L", "R", "S", "U", "A", "X"):
                    blink = len(head) > 1 and head[1] == "B"
                    cmd = d + ("B" if blink else "")
                    cmd_queue.append((cmd, street, dist, conn))
                    print("BLE rx:", cmd, street or "", dist or "")
                else:
                    print("unknown cmd:", head)


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
    global cur_dir, cur_blink, cur_dist, need_advertise, adv_retry_at
    lcd_setup()
    show_idle()
    ble_setup()
    print("CitiNav ready: ui=v%d name=%s svc=%s cmd=%s"
          % (VERSION, BLE_NAME, _UUID_SVC, _UUID_CMD))

    visible = True
    last_blink = time.ticks_ms()
    next_cmd_at = 0

    while True:
        now = time.ticks_ms()

        # (re)start advertising after a disconnect, retrying on failure
        if need_advertise and time.ticks_diff(now, adv_retry_at) >= 0:
            try:
                advertise()
                need_advertise = False
                print("advertising again")
            except Exception as e:
                print("advertise retry:", e)
                adv_retry_at = time.ticks_add(now, 500)

        # take the next queued command (respecting the on-screen hold time)
        if cmd_queue and time.ticks_diff(now, next_cmd_at) >= 0:
            cmd, street, dist, conn = cmd_queue.pop(0)
            d = cmd[:1]
            if d in ("L", "R", "S", "U", "A", "X"):
                cur_dir = d
                cur_blink = len(cmd) > 1 and cmd[1] == "B"
                cur_dist = dist
                if street is not None:
                    STREETS[d] = street[:10]
                if d in ("L", "R", "S"):
                    show_dir(cur_dir, cur_blink)
                elif d == "U":
                    show_uturn(cur_blink)
                elif d == "A":
                    show_arrive()
                else:                                  # X -> clear to idle
                    show_idle()
                visible = True
                last_blink = now
                next_cmd_at = time.ticks_add(now, HOLD_MS)
                # ack back to the sender (best-effort)
                try:
                    if conn in connections:
                        ble.gatts_notify(conn, st_handle,
                                         b"ack:" + cmd.encode())
                except Exception:
                    pass
                print("showing %s street=%r dist=%r blink=%s"
                      % (cur_dir, STREETS.get(d, ""), cur_dist, cur_blink))
            else:
                print("unknown cmd:", cmd)

        # blink the active arrow (box stays put)
        if cur_blink and cur_dir in ("L", "R", "S", "U"):
            if time.ticks_diff(now, last_blink) >= BLINK_MS:
                visible = not visible
                last_blink = now
                if cur_dir == "U":
                    tft.fill_rect(0, ARROW_Y0, W, ARROW_H, BG)
                    if visible:
                        arrow_uturn(W // 2, ARROW_CY, ARROW)
                else:
                    draw_arrows(cur_dir, visible)

        time.sleep_ms(20)


if __name__ == "__main__":
    main()
