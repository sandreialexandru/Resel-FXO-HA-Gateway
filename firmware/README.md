# Firmware

Put the ESPHome YAML of the gateway in this folder (for example `resel-fxo-gateway.yaml`).

The behaviour of the firmware is described in detail in [`../hardware/README.md`](../hardware/README.md), section 3.

## What the YAML needs

- **Board**: ESP32 (ESP-IDF framework).
- **Secrets** (`secrets.yaml`): `wifi_ssid`, `wifi_password`, `audio_token`.
  The `audio_token` must be the same value you enter in the Home Assistant integration.
- **External component** `audio_tcp`, pulled from this repository:

  ```yaml
  external_components:
    - source: github://sandreialexandru/Resel-FXO-HA-Gateway@main
      components: [audio_tcp]
  ```

- **Ring detection**: the switch *Interfon Detectie Sonerie ADC* must be **ON** (it is the detector that works on rev C).
  The entity `Interfon Sonerie` is the one to use in automations; *Sonerie Brut (diag)* and *Sonerie Impuls IO33* are diagnostics only.

## Files

Add your own files here. Nothing is generated automatically.
