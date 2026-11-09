#!/Users/zakaria/.esptool-venv/bin/python
"""CitiNav terminal sender - write arrows + street text to the ESP32 over BLE.

Usage:
    python citinav_send.py                           # interactive prompt
    python citinav_send.py L R S                     # send listed commands, then exit
    python citinav_send.py "L:W 4th St" "R:Broadway"  # arrows with street text

Commands:  L R S        -> static arrow (left / right / straight)
           LB RB SB     -> same arrow, blinking
           L:Street name -> arrow plus the street shown in the top banner
           ;             -> separates multiple commands in the prompt
           Q             -> quit

Install:   pip install bleak
macOS:     grant your terminal Bluetooth access in
           System Settings > Privacy & Security > Bluetooth
"""

import asyncio
import sys
import threading
from bleak import BleakScanner, BleakClient

NAME     = "CitiNav"
CMD_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
ACK_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

HELP = "L R S U = arrows  A arrive  X clear  LB RB SB UB = blink  L:Street  ; separates  Q=quit"


def on_ack(_sender, data):
    try:
        print("   ack:", data.decode())
    except Exception:
        print("   ack:", data)


def valid_cmd(token):
    """True if token is a direction command, optionally with ':street'."""
    t = token.strip()
    if not t:
        return False
    head = t.split(":", 1)[0].strip().upper()
    return head in ("L", "R", "S", "U", "A", "X", "LB", "RB", "SB", "UB")


async def send(client, token):
    t = token.strip()
    if not valid_cmd(t):
        print("!  use one of:  L R S U A X   LB RB SB UB   or   L:Street name")
        return
    await client.write_gatt_char(CMD_UUID, t.encode(), response=True)
    print("   sent", t)


async def run(one_shot):
    print("scanning for", NAME, "...")
    dev = await BleakScanner.find_device_by_name(NAME, timeout=20)
    if dev is None:
        print("!  %s not found - is the board powered and showing 'CitiNav'?" % NAME)
        return

    async with BleakClient(dev, timeout=20) as client:
        print("connected:", dev.address)
        try:
            await client.start_notify(ACK_UUID, on_ack)
        except Exception as e:
            print("(ack notifications unavailable: %s)" % e)

        if one_shot:
            for ch in one_shot:
                await send(client, ch)
        else:
            print(HELP)
            loop = asyncio.get_running_loop()
            queue = asyncio.Queue()
            # Read stdin on a daemon thread instead of run_in_executor(): on
            # Python 3.14 the executor future is cancelled on Ctrl-C and dumps
            # a CancelledError traceback (and a blocked input() can hang exit).
            threading.Thread(target=_stdin_reader,
                             args=(loop, queue), daemon=True).start()
            while True:
                line = await queue.get()
                if line is None:                 # EOF (Ctrl-D)
                    break
                line = line.strip()
                if not line:
                    continue
                if line.upper() == "Q":
                    break
                for tok in line.split(";"):
                    await send(client, tok)

        print("disconnecting")


def _stdin_reader(loop, queue):
    """Feed stdin lines into an asyncio.Queue from a daemon thread."""
    while True:
        try:
            line = input("cmd> ")
        except EOFError:
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        loop.call_soon_threadsafe(queue.put_nowait, line)


def main():
    try:
        asyncio.run(run(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
