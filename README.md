# Resel FXO HA Gateway

Answer your building intercom from Home Assistant: detect the ring, pick up, talk, and open the door, from the phone or a wall tablet.

The project connects the **interior unit of a Resel building intercom** (a phone-style "post interior" on a 2-wire POTS-like line) to **Home Assistant** through a small ESP32 + audio codec + discrete FXO circuit. It has three parts:

| Part | Folder | What it does |
|---|---|---|
| ESPHome component `audio_tcp` | [`components/audio_tcp`](components/audio_tcp) | TCP server on the ESP32 that streams the line audio out and plays audio received from a client |
| Home Assistant integration `resel_fxo_gateway` | [`custom_components/resel_fxo_gateway`](custom_components/resel_fxo_gateway) | Bridges the ESP32 audio port to the browser through the Home Assistant websocket, and serves the card |
| Lovelace card `resel-intercom-card` | [`custom_components/.../frontend`](custom_components/resel_fxo_gateway/frontend/resel-intercom-card.js) | Answer, hang up, push-to-talk, live line level, four custom buttons |

Everything else (ring detection, hook control, dialing, codec setup) is plain ESPHome YAML on the ESP32 and uses the standard Home Assistant ESPHome integration.

> **Status: hobby project, partly tested.** Ring detection, answering, hang-up, pulse and DTMF dialing, and audio from the intercom to the ESP32 work on the real line. See [Status](#status) for what is and is not verified.

---

## How it works

```mermaid
flowchart LR
  P[Resel panel / building line] --- L[FXO circuit<br/>ring detect + hook + 1:1 transformer]
  L --- C[WM8960 codec<br/>I2S 16 kHz]
  C --- E[ESP32 + ESPHome]
  E -- ESPHome API<br/>entities, buttons --> HA[Home Assistant]
  E -- TCP :6054<br/>PCM 16 kHz --> B[resel_fxo_gateway<br/>bridge]
  B -- websocket<br/>base64 PCM --> W[Browser: Intercom card]
```

- **Control** (ring state, answer, hang up, door, PTT switch, levels) goes over the normal ESPHome API.
- **Voice** goes over a separate TCP connection from the ESP32 to Home Assistant, then over the Home Assistant websocket to the card. This is deliberately not SIP: it is small enough to run on a classic ESP32 without PSRAM.
- **Half duplex.** The official ESPHome `i2s_audio` cannot run the microphone and the speaker at the same time on one bus, so the line is either *listening* (microphone on) or *talking* (speaker on). The push-to-talk switch toggles between the two.

### Call flow

1. Someone rings from the panel. The ring detector latches, `Interfon Sonerie` turns on and a `esphome.resel_ring` event is fired.
2. **Answer** lifts the hook (GPIO32 high) and starts listening. The card shows the line audio.
3. **Hold to talk** turns the PTT switch on: the ESP32 stops the microphone, switches the speaker on and accepts audio from the card. Releasing returns to listening.
4. **Open door** dials `0` (pulse or DTMF, selectable) and puts the line back on hook. The panel ends the call after opening the door.

### Audio transport (`audio_tcp`)

Plain TCP, one client at a time (a newer client replaces the old one):

1. Client sends one ASCII line: `AUDIO1 <token>\n` (a wrong token closes the connection).
2. ESP32 → client: raw PCM, 16 kHz, 16-bit, mono, only while the line is being listened to.
3. Client → ESP32: raw PCM for the speaker, accepted only while PTT is on.

The Home Assistant side keeps **one** connection to the ESP32 and fans it out to every open card, so a phone and a wall tablet can watch the same call. The connection is opened only while at least one card is in a call. Websocket commands (`resel_fxo_gateway/subscribe_audio`, `resel_fxo_gateway/send_audio`) are admin-only.

---

## What we know about the Resel system

- Resel "Interfon de scară cu carduri de proximitate": exterior central unit, power supply (5 V / 12 V / 48 V DC, 12 V battery backup recommended), floor distributors, and the interior post in each apartment, connected with RJ11 on 2 wires.
- The interior post is a wall-mounted keypad phone working in **tone (DTMF)** mode with a dual-tone ringer. It has a TONE/PULSE switch and a RINGER ON/OFF switch.
- Resel support: the line follows the PBX standard as closely as possible, and the ring signal is **75–120 V AC at about 27 Hz**.
- Measured on a multimeter: on hook the line sits around **50 V**; during a ring the AC voltage jumps to about **50–60 V** and drops to 0 in a repeating burst pattern.
- Measured with the ESP32 circuit: with the hook output high the line reads about **8 V**, the same as with the handset lifted.
- The speaker and microphone gain potentiometers are on the exterior central unit, not in the apartment.
- **The door opens with key `0`.** It works with both pulse and tone dialing on the post. `008` switches the stair light, and `#0` calls the building panel (tone mode).
- The panel closes the call after opening the door, so the firmware always puts the line back on hook after a door command.
- Calls last at most about one minute, so the firmware watchdog (v7h) releases the line after 1 minute.

Note: the commercial Emblyx controller for Resel systems offers Apple Home, Google Home and Alexa support, but at the time of writing no Home Assistant integration and no audio.

---

## Hardware

A short overview only; the full schematic is not part of this repository.

| Block | Part / value | Role |
|---|---|---|
| MCU | ESP32 DevKitC (WROOM-32E), ESPHome on ESP-IDF | Everything digital |
| Audio codec | WM8960 breakout, 24 MHz on-board oscillator, no MCLK pin | Line ↔ I2S, 16 kHz; codec PLL makes 12.288 MHz SYSCLK |
| Line isolation | 1:1 600 Ω audio transformer (SM-LP-5001) | Galvanic isolation for voice |
| Ring detection | Series 0.47 µF / 275 V capacitor, bridge, TVS, PC817-type optocoupler, RC network on `RING_DET` | High-impedance ring sensing |
| Hook control | Transistor driving an optocoupler + load resistor | Off-hook (answer, pulse dialing) |

ESP32 pins:

| Function | GPIO |
|---|---|
| I2C SDA / SCL (codec control, 0x1A) | 21 / 22 |
| I2S BCLK / LRCLK | 27 / 26 |
| I2S DACDAT (ESP32 → codec) | 25 |
| I2S ADCDAT (codec → ESP32) | 35 |
| Hook control (high = off-hook, held low by 10 kΩ resistors at boot) | 32 |
| Ring detection node (digital + ADC) | 34 |

Safety: the hook output is held low in hardware, so the line cannot go off-hook while the ESP32 is in reset or booting. The firmware also drops the line after a watchdog timeout. **The line side carries ring voltage (75–120 V AC); build and test with care.**

---

## Measured values

All measured on the real line of the author's apartment.

### Ring detection

| Item | Value |
|---|---|
| `RING_DET` node at rest | about 0.14 V (ADC offset) |
| Node on a ring (final circuit, R = 3 MΩ, C = 0.47 µF) | **2.8–3.1 V** peak |
| Time constant of the node | about 1.4 s |
| Time above the ESP32 digital threshold (≈ 2.5 V) on a short ring | about 0.3 s |
| Node with the first circuit (R = 330 kΩ, 4.7 µF electrolytic) | only 0.45–0.55 V, not detected |
| Digital filter | `delayed_on: 50 ms` |
| ADC detector (optional) | rise at ≥ 0.5 V, fall below 0.4 V |
| Ring hold time | 6 s without signal (the ring cadence has pauses of 2–4 s) |
| Lockout after any hook change | 4 s (the hook itself disturbs the node) |

### Dialing

| Item | Value |
|---|---|
| Pulse | 60 ms break + 40 ms make (10 pulses/s), 800 ms between digits, `0` = 10 pulses |
| DTMF | 400 ms tone + 150 ms gap per key, amplitude 28000/32767 |
| Wait after off-hook before dialing | 1.5 s |
| Door command cooldown | 10 s |

### Audio

| Item | Value |
|---|---|
| Format | 16 kHz, 16-bit, mono |
| Line noise floor (nobody speaking) | RMS about **−62 dBFS**, DC offset about 0 |
| Content | dominated by **50 Hz mains hum** and its odd harmonics |
| Band 300–3400 Hz | about **−72 dBFS** |
| Fix | notch comb on 50 Hz multiples + high-pass 300–350 Hz in the card (noise −63 → −83 dBFS) |
| Card level meter | `−90 dBFS` means the clamp floor (microphone stopped), not measured noise |
| Streaming chunk | 40 ms (640 samples) |
| Playback jitter buffer in the card | about 120 ms, dropped if more than 800 ms behind |
| PTT safety timeout | 30 s on the ESP32 |

---

## Installation

### 1. ESP32 (ESPHome)

Add the external component from this repository:

```yaml
external_components:
  - source: github://sandreialexandru/Resel-FXO-HA-Gateway@main
    components: [audio_tcp]

audio_tcp:
  id: audio_hub
  port: 6054
  token: !secret audio_token      # any password; the same one goes into Home Assistant
  speaker: intercom_speaker       # your i2s_audio speaker
```

In the microphone `on_data` lambda, forward blocks with `id(audio_hub).push_mic((const uint8_t *) x.data(), bytes);`. On PTT switch on/off call `id(audio_hub).set_talk(true/false);`. The full firmware (codec init, ring detection, hook control, dialing, PTT) is not published here yet.

Needs ESP-IDF and a recent ESPHome (developed on 2026.9).

### 2. Home Assistant integration (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/sandreialexandru/Resel-FXO-HA-Gateway`, type **Integration**.
2. Download **Resel FXO HA Gateway** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → *Resel FXO HA Gateway*: host of the ESP32, port `6054`, token.
4. The card file is registered automatically. Hard refresh the browser after an update.

Manual install: copy `custom_components/resel_fxo_gateway` to `/config/custom_components/`.

> The browser microphone needs a **secure context**: open Home Assistant over **HTTPS** (or `localhost`, or the companion app with microphone permission granted).

### 3. Card

```yaml
type: custom:resel-intercom-card
entity_prefix: resel_fxo_gateway_interfon_    # or set every entity below
entities:
  state: sensor.resel_fxo_gateway_interfon_stare
  answer: button.resel_fxo_gateway_interfon_raspunde
  hangup: button.resel_fxo_gateway_interfon_inchide
  ptt: switch.resel_fxo_gateway_interfon_ptt
  level: sensor.resel_fxo_gateway_interfon_nivel_microfon_rms
ptt_mode: hold            # hold | toggle
gain: 2                   # playback gain for the line audio
mic_gain: 1               # gain for your microphone
highpass_hz: 250          # removes the 50 Hz hum (0 = off)
lowpass_hz: 3400
notch_hz: 50              # mains hum filter: notches on 50 Hz and its multiples (60 for 60 Hz grids, 0 = off)
show_timer: false
buttons:                  # shown 2 per row under the PTT button
  - name: Open door
    icon: mdi:door-open
    entity: button.resel_fxo_gateway_interfon_deschide_usa
  - name: Stair light
    icon: mdi:lightbulb-on-outline
    entity: button.resel_fxo_gateway_interfon_lumina_scara_008
  - name: Call panel
    icon: mdi:phone-outgoing
    entity: button.resel_fxo_gateway_interfon_cheama_panoul_0
    disabled_when: [in_call]
  - name: Mute mic
    entity: switch.resel_fxo_gateway_interfon_mute_audio
    icon: mdi:microphone
    state_icons: { "on": mdi:microphone-off, "off": mdi:microphone }
    state_colors: { "on": red }
```

Card options:

- **Buttons:** each takes `name`, `icon`, `entity` (button, script, scene, switch, light… act sensibly by domain) or a `tap_action` (`perform-action`, `toggle`, `more-info`, `navigate`, `url`). Extra keys: `disabled_when` (list of `idle`, `ringing`, `connecting`, `listening`, `talking`, `in_call`), `state_icons`, `state_colors`.
- **Hum filter:** the line noise is mostly 50 Hz and its harmonics. The card applies a comb of narrow notches (`notch_hz`, up to `notch_max_hz: 1500`, `notch_q: 30`), then the high-pass and low-pass. On a recording of the idle line this took the noise from −63 dBFS to −83 dBFS (high-pass/low-pass alone: −73 dBFS).
- **Texts:** all UI texts are English and can be overridden with `labels:`.
- **card-mod:** the root is `<ha-card>` and every part has a class (`.header`, `.status`, `.meter`, `.answer`, `.hangup`, `.ptt`, `.custom`). Custom buttons expose `data-state`, for example `.custom[data-state="on"] { … }`.
- **Status strings:** the card expects the ESPHome text sensor to report `Inactiv`, `Suna`, `Conectare`, `In apel - ascult` and `In apel - vorbesc`.

**Troubleshooting: "Custom element doesn't exist: resel-intercom-card".** The integration loads the card by itself, so no Lovelace resource is needed. If you added one by hand earlier, delete it (Settings → Dashboards → Resources), otherwise the card is loaded twice, possibly in an old version. The card file is cached by the browser/companion app (its URL carries the version), so after the first download it is available at once, even when the app restarts on another network. If the error still shows up after switching networks, the script request itself failed: in the companion app use Settings → Companion app → Troubleshooting → *Reload frontend* (or clear the frontend cache).

---

## Status

**Works on the real line**

- Ring detection (digital and optional ADC), including the 6 s hold and the post-hook lockout
- Off-hook, hang-up, 1-minute watchdog
- Pulse dialing: door opens with `0`, other numbers can be dialed
- DTMF dialing for the building panel (`#0`)
- Continuous real-time audio from the intercom to the ESP32 and over TCP to a client
- Token handshake, PTT switch, microphone/speaker hand-over in the ESP32 logs

**Verified in a test environment only**

- The bridge against a simulated ESP32 (token ok / wrong token / no server, odd-length reads)
- The card in a headless browser with a simulated Home Assistant (states, PTT streaming, buttons, `disabled_when`, `state_icons`)

**Not yet verified**

- Voice level at the panel with someone speaking, and intelligibility of the voice sent *to* the panel
- Door opening with a DTMF `0` (pulse works)
- Microphone permission and audio in the Home Assistant companion app and Fully Kiosk
- Running with several cards open at the same time on real devices

**Known limits**

- Half duplex only (push-to-talk), single ESP32 client at a time
- Latency and quality are those of a 16 kHz PCM stream over websocket, with no echo cancellation on the line side
- No visual card editor (YAML only)
- Tested on classic ESP32 + WM8960; other codecs would need their own init and gain tuning

---

## Repository layout

```
components/audio_tcp/                 ESPHome external component (C++)
custom_components/resel_fxo_gateway/  Home Assistant integration
  frontend/resel-intercom-card.js     Lovelace card
hacs.json                             HACS metadata
.github/workflows/release.yml         creates a release when the manifest version changes
```

## Credits

Built with the help of Claude (Anthropic).
