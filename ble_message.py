# LCD147 - BLE GATT server: send a message from your phone -> shows on LCD
#
# Service UUID : 12345678-1234-5678-1234-56789abcdef0
#   Message char (WRITE/READ) : ...def1   <- write text here
#   Status  char (READ/NOTIFY): ...def2   <- replies "received: ..."
#
# Connect with nRF Connect / LightBlue, write a string to the Message
# characteristic, and it appears on the display.

import gc
import os
import time
import machine
import bluetooth
from micropython import const
from machine import Pin, SPI
import st7789py as st7789
import vga1_8x16 as font

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

BLE_NAME = "ESP32-C6-LCD"
COLS = 21                    # characters per line (172 px / 8 px)

# ---- BLE event / flag constants ----
_IRQ_CENTRAL_CONNECT    = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE        = const(3)

_FLAG_READ             = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE            = const(0x0008)
_FLAG_NOTIFY           = const(0x0010)

_UUID_SVC = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef0")
_UUID_MSG = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef1")
_UUID_ST  = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef2")

_CHAR_MSG = (_UUID_MSG, _FLAG_READ | _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
_CHAR_ST  = (_UUID_ST,  _FLAG_READ | _FLAG_NOTIFY)
_SERVICE  = (_UUID_SVC, (_CHAR_MSG, _CHAR_ST))

# ---- globals ----
ble = None
tft = None
msg_handle = None
st_handle = None
connections = set()
pending = None


# ================= LCD =================

def row(y, label, value, lc=st7789.GREEN, vc=st7789.WHITE):
    tft.text(font, label, 4, y, lc)
    vx = 4 + len(label) * 8 + 6
    if vx + len(value) * 8 > 172:
        y += 16
        vx = 4
    tft.text(font, value, vx, y, vc)
    return y + 16


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


def draw_specs():
    mac = ":".join("%02X" % b for b in machine.unique_id())
    freq = machine.freq() // 1_000_000
    free_kb = gc.mem_free() // 1024
    st = os.statvfs("/")
    fs_total = st[0] * st[2] // 1024
    fs_free = st[0] * st[3] // 1024
    rows = (
        ("Chip",  "ESP32-C6FH8"),
        ("Rev",   "v0.2 QFN32"),
        ("CPU",   "%d MHz" % freq),
        ("Flash", "8 MB"),
        ("WiFi",  "Wi-Fi 6 (2.4G)"),
        ("BT",    "Bluetooth 5 LE"),
        ("uPy",   "v" + os.uname().release),
        ("RAM",   "%d KB free" % free_kb),
        ("FS",    "%d/%d KB" % (fs_free, fs_total)),
        ("MAC",   mac),
    )
    tft.fill(st7789.BLACK)
    tft.fill_rect(0, 0, 172, 22, st7789.BLUE)
    tft.text(font, "ESP32-C6 SPECS", 6, 3, st7789.WHITE)
    y = 30
    for label, value in rows:
        y = row(y, label, value)
    y = row(y, "BLE", "advertising", st7789.GREEN, st7789.YELLOW)
    tft.text(font, BLE_NAME, 4, y, st7789.CYAN)
    tft.text(font, "write via BLE ->", 4, y + 16, st7789.WHITE)


def wrap(text, cols=COLS):
    out = []
    for raw in text.split("\n"):
        line = ""
        for word in raw.split():
            while len(word) > cols:            # break very long words
                if line:
                    out.append(line); line = ""
                out.append(word[:cols]); word = word[cols:]
            cand = (line + " " + word) if line else word
            if len(cand) <= cols:
                line = cand
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def show_message(text):
    tft.fill(st7789.BLACK)
    tft.fill_rect(0, 0, 172, 22, st7789.MAGENTA)
    tft.text(font, "BLE MESSAGE", 6, 3, st7789.WHITE)
    y = 34
    for line in wrap(text):
        if y > 300:
            break
        tft.text(font, line, 4, y, st7789.WHITE)
        y += 16


# ================= BLE =================

def advertise():
    adv = bytearray([0x02, 0x01, 0x06])                 # flags
    n = BLE_NAME.encode()
    adv += bytes([len(n) + 1, 0x09]) + n                # complete local name
    su = bytes(_UUID_SVC)
    resp = bytes([len(su) + 1, 0x07]) + su              # 128-bit service UUID
    ble.gap_advertise(100000, adv_data=adv, resp_data=resp)


def irq(event, data):
    global pending
    if event == _IRQ_CENTRAL_CONNECT:
        conn, _, _ = data
        connections.add(conn)
        print("BLE: phone connected")
    elif event == _IRQ_CENTRAL_DISCONNECT:
        conn, _, _ = data
        connections.discard(conn)
        print("BLE: disconnected -> re-advertising")
        advertise()
    elif event == _IRQ_GATTS_WRITE:
        conn, attr = data
        if attr == msg_handle:
            raw = ble.gatts_read(msg_handle)
            try:
                pending = raw.decode().strip()
            except Exception:
                pending = "0x" + raw.hex()
            print("BLE rx:", pending)


def ble_setup():
    global ble, msg_handle, st_handle
    ble = bluetooth.BLE()
    ble.active(True)
    try:
        ble.config(gap_name=BLE_NAME)
    except Exception:
        pass
    try:
        ble.config(mtu=247)                 # allow longer messages
    except Exception:
        pass
    ((msg_handle, st_handle),) = ble.gatts_register_services((_SERVICE,))
    ble.gatts_write(st_handle, b"ready")
    ble.irq(irq)
    advertise()


# ================= main =================

def main():
    global pending
    lcd_setup()
    draw_specs()
    ble_setup()
    print("BLE GATT ready: name=%s svc=%s msg=%s"
          % (BLE_NAME, _UUID_SVC, _UUID_MSG))

    while True:
        if pending is not None:
            text = pending
            pending = None
            show_message(text)
            try:
                if connections:
                    ble.gatts_write(st_handle, ("received: " + text)[:20].encode())
                    for c in connections:
                        ble.gatts_notify(c, st_handle)
            except Exception as e:
                print("notify err:", e)
        time.sleep_ms(50)


if __name__ == "__main__":
    main()
