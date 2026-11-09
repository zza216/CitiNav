# CitiNav — Test Card

**Build under test:** Web Nav v4 (`webapp/index.html`) + firmware v2
(`citinav_landscape.py`), device on the handlebars, phone in pocket, page served
over a Cloudflare tunnel.
**Date / facilitator:** ______________  **Participant #:** ______

---

## Assumption

We believe **a regular urban cyclist** can **follow a 1.5–2 km route with 4–6
turns using only the handlebar device, with the phone in their pocket and without
looking at the phone screen**, in **a real, low-traffic street setting**.

(If this is false, the whole "phone is the brain, device is the display" premise
needs rethinking.)

---

## Comparison

| | What they do today | What they do with the prototype |
|---|---|---|
| **Setup** | Mount the phone (or hold it) and run Google Maps bike navigation | Phone stays **in pocket**; device mounted on the bars |
| **During the ride** | Glance at the phone screen for the next turn; audio cues optional | Read the **arrow + street + distance** on the device; it **blinks within 30 m** |
| **Attention** | Eyes leave the road to check the phone | Eyes stay on the road; no phone screen needed |
| **Failure mode** | Missed turn → stop, re-check phone | Missed turn → device shows the next turn; no phone needed |

**Baseline to capture first:** the same participant rides the same route once with
Google Maps on the phone (their normal method). Record time, phone glances, and
missed turns. Then repeat with the prototype.

---

## Observation

Watch and record (don't coach):

| Signal | How to measure | Baseline | Prototype |
|---|---|---|---|
| **Finished the route** | Reached destination without facilitator help (Y/N) | | |
| **Missed turns** | Count of turns taken wrong / not taken | | |
| **Phone glances** | Count of times they looked at/unlocked the phone | | |
| **Total time** | Start → destination (mm:ss) | | |
| **Reaction to blink** | Did they turn within ~10 m of the blink starting? (Y/N) | | |
| **Asked for help** | Count of facilitator prompts / questions | | |
| **Re-opened / reconnected** | Did they reopen the app or reconnect BLE? (Y/N) | | |
| **BLE uptime** | Connected for the whole ride? (Y/N, or % ) | | |
| **Comprehension** | Could they say what the device was showing? (Y/N) | | |
| **Trust / confidence** | 1–5 ("I knew when to turn") | | |
| **Would use again** | Y/N | | |

**Definitions**
- *Mistake* = a turn taken in the wrong direction, a turn missed and corrected, or
  a stop to figure out where to go.
- *Phone glance* = any look at the phone screen (not just unlocking).
- *Help* = any facilitator hint beyond the initial briefing.

**Also note (free text):** confusion about blink vs. static, distance readability,
street-name truncation, glare/sunlight, mount position, GPS drift, battery/heat.

---

## Decision rule

**Keep going (green) if, across 5 participants:**
- ≥ 4 / 5 finish the route with **≤ 1 missed turn**, and
- average **≤ 2 phone glances** per ride, and
- **no facilitator help** needed, and
- BLE connected for the **whole ride** (no reconnects), and
- ≥ 4 / 5 say they'd use it again and rate confidence ≥ 4 / 5.

**Change it (red) if any of:**
- ≥ 2 participants miss a turn **because the arrow/blink was unclear**, or
- average **≥ 3 phone glances** (they still rely on the phone), or
- any **BLE drop** that forced a reconnect, or
- participants **can't tell when to turn** from the device, or
- the prototype is **not faster / not fewer glances** than their Google Maps baseline.

**Iterate (amber):** anything between green and red — keep the concept, fix the
specific failure (e.g., blink threshold, distance wording, mount angle) and retest.

---

## Run sheet (5 min)

1. Brief: "Follow the route to the destination. Use the device however you like.
   I won't help unless you ask." (Don't explain the blink.)
2. Baseline ride with Google Maps → record.
3. Prototype ride → record.
4. Debrief: "What was the device telling you? When did you know to turn? What was
   confusing?" (3 questions, no leading.)
5. Log the table above; mark green / amber / red.

**Route requirements:** low-traffic, 1.5–2 km, 4–6 turns, at least one long
straight and one close-together pair of turns; daylight; dry.
