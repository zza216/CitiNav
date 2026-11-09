# GUI Design for Small-Memory Devices (ESP32-C6 + 172×320 LCD)

*How to design CitiNav's on-device user interface to fit a microcontroller with
no PSRAM and a few hundred KB of free RAM.*

**Target:** ESP32-C6FH8 · 512 KB SRAM (no PSRAM) · MicroPython v1.29 · 1.47" 172×320 ST7789

---

## 1. The core constraint

The ESP32-C6 has **no PSRAM** — only 512 KB SRAM total, of which MicroPython
leaves roughly **~300 KB free heap** at boot. The display is **172×320** pixels.

Everything below is a trade-off between **RAM**, **code complexity**, and
**visual quality**. The guiding principle:

> **Never hold a whole screen in RAM unless you truly need to.**
> The ST7789 keeps the image in its **own internal GRAM** (240×320), so a host
> framebuffer is only needed when you must *composite* or *animate*.

## 2. Memory budget

| Buffer / asset | Size (RGB565 unless noted) | % of ~300 KB free heap |
|---|---|---|
| Full screen 172×320 | **107 KB** | ~36 % |
| Half screen 172×160 | 54 KB | ~18 % |
| Tile 172×40 | 13.8 KB | ~5 % |
| Tile 172×16 (one text line) | 5.4 KB | ~2 % |
| Scanline 172×1 | 344 B | ~0.1 % |
| 1-bit line (172 px) | 22 B | ~0 |
| `vga1_8x16` font (flash) | 6.7 KB | 0 (flash) |
| `vga2_bold_16x32` font (flash) | 66 KB | 0 (flash) |

> Fonts/icons stored as **frozen modules / `bytes`** cost RAM only while
> referenced, and the bulk lives in flash.

## 3. Architecture options (lightest → heaviest)

### Option A — Direct drawing / dirty rectangles ⭐ (no framebuffer)
Draw primitives straight to the panel; erase by over-painting a filled rect;
track which regions changed and redraw only those.

- **RAM:** ~0
- **Pros:** tiny footprint; excellent for static or simple screens
- **Cons:** you manage "dirty" regions; erasing large areas then redrawing can flicker
- **Best for:** status screens, single-purpose UIs — **this is the correct choice for CitiNav's arrow screen**

### Option B — Scanline / strip streaming
Build one line (or a short strip) in a small buffer and push it repeatedly.

- **RAM:** hundreds of bytes – few KB
- **Pros:** very low RAM, smooth horizontal motion
- **Cons:** only works for content you can render row-by-row
- **Best for:** waveforms, graphs, scrolling tickers

### Option C — Partial (tile) framebuffer ⭐ (sweet spot for richer UI)
Keep one or a few **small tiles** in RAM, render into them with `framebuf`, then blit to the target window.

- **RAM:** 5–15 KB per tile
- **Pros:** smooth animation, can use `framebuf` shapes/text, still low RAM
- **Cons:** compositing across tiles is manual
- **Best for:** menus, gauges, animated widgets — the upgrade path if CitiNav's UI grows

### Option D — Full framebuffer
- **RAM:** 107 KB (leaves ~190 KB for app logic)
- **Pros:** trivial, flexible drawing
- **Cons:** heavy on a 512 KB part; also needs a **byte swap** (panel is big-endian, `framebuf` is little-endian)
- **Best for:** only if you really need arbitrary compositing and can spare the RAM

### Option E — Double buffering
- **RAM:** ~214 KB → **not realistic** on this chip

## 4. Library / stack options

| Option | RAM model | When to use |
|---|---|---|
| **Hand-rolled primitives** (current) | none | Best fit for CitiNav today |
| **`nano-gui` / `ugui` / `micropython-touch`** (Peter Hinch) | partial framebuffer | Best *library* option on small RAM — widgets, meters, dials in pure Python |
| **LVGL** (`lv_binding_micropython`) | partial buffers, but requires a **custom C firmware build** | Rich, animated multi-screen UI — heavy dependency for a no-PSRAM part |
| **Arduino / ESP-IDF + LVGL or `esp_lcd`** | C, hardware-accelerated | If a *polished* GUI matters more than staying in MicroPython |

> The generic MicroPython ESP32-C6 build does **not** include LVGL or `esp.LCD`.
> Adding either means **building custom firmware**.

## 5. Low-RAM techniques (use with any option)

1. **Keep assets in flash, not RAM.** Fonts/icons as frozen modules or `bytes`
   (`vga1`, `vga2` already work this way).
2. **Use the ST7789's own features:**
   - **Partial windows** (`CASET`/`RASET`) → update only the changed rectangle.
   - **Hardware vertical scroll** (`VSCRDEF` `0x33` / `VSCSAD` `0x37`, already in
     `st7789py`) → scroll logs/menus with ~0 RAM.
   - **Display on/off** and **partial mode** to avoid full redraws.
3. **Indexed-colour sprites.** 1-bit/4-bit icons (32×32 = 128 B at 1-bit vs 2 KB at 16-bit).
4. **Pre-render, then recompute on change** — don't cache full screens.
5. **Preallocate buffers once** (avoid per-frame allocation → GC churn and heap
   fragmentation).
6. **Skip alpha and anti-aliasing** — `framebuf` has neither; 1-bit text is cheapest.
7. **`@micropython.native` / `@micropython.viper`** on hot draw loops — helps
   speed, not RAM.

## 6. Recommendation for CitiNav

| Stage | UI need | Approach |
|---|---|---|
| **Now** | boot splash + 3 arrows + street + label (landscape v2) | **Option A** (direct draw + dirty rects) — zero RAM, already smooth |
| **Next** | add distance / ETA / speed | **Option A** + small change-ticks; only redraw numeric fields |
| **If it grows** | menus, mini-map, gauges | **Option C** (partial tiles) + `nano-gui` + hardware scroll for lists |
| **Only if needed** | polished animated multi-screen UI | move that part to **ESP-IDF/Arduino + LVGL**, or use a **PSRAM** board |

**Dirty-rectangle pattern for CitiNav:**

```python
# only repaint the regions that change
def set_arrow(new_dir, blink):
    if new_dir != cur["dir"] or blink != cur["blink"]:
        clear_rect(ARROW_X, ARROW_Y0, ARROW_W, ARROW_H)  # erase arrow only
        draw_arrow(new_dir)                              # redraw arrow only
        # banner + label untouched
```

## 7. Current CitiNav UI — as-built budget (UI v2, landscape)

The active firmware (`citinav_landscape.py`) rotates the panel to **320×172
landscape** and — like v1 — draws directly, with **~0 RAM**.

| Region | Technique | RAM |
|---|---|---|
| Boot splash (`CitiNav`) | full `fill(BG)` + yellow `bigfont` title | 0 (font in flash) |
| Top banner (street) | direct `fill_rect` + `bigfont` text (bg = banner colour) | 0 |
| Three-arrow row | direct `fill_rect`/`rect`/`hline` + triangle fill | 0 |
| Active-arrow box | `rect` outline in green | 0 |
| U-turn / ARRIVED / clear | direct draw (glyph · `bigfont` · idle screen) | 0 |
| Bottom label | direct `fill_rect` + `font` text (bg = page colour) | 0 |
| Blink loop | timer + redraw the arrow row only | 0 |

**No black text boxes:** `st7789py.text()` always fills a character background, so
the code passes the surrounding colour — `BG` (dark grey) for page text and
`BANNER` for the street name — instead of the default black.

**Total GUI RAM: ~0 bytes** — everything lives in the display's GRAM and flash.
The only heap use is the driver object, fonts (flash) and normal Python overhead.

---

### Quick decision guide

```
Is the screen mostly static / a single purpose?
   └─ yes → Option A (direct draw + dirty rects)      ← CitiNav

Do you need smooth animation or several widgets?
   └─ yes → Option C (partial tiles) + nano-gui

Do you need a rich, animated, multi-screen UI?
   └─ yes → rebuild on ESP-IDF/Arduino + LVGL, or use a PSRAM board
```
