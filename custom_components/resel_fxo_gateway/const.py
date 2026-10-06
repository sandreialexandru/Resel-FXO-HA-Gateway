"""Constants for the Resel FXO HA Gateway integration."""

DOMAIN = "resel_fxo_gateway"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_TOKEN = "token"

DEFAULT_PORT = 6054

# Audio format used by the ESP audio_tcp component: PCM, 16 kHz, 16 bit, mono.
SAMPLE_RATE = 16000
# 40 ms of audio per read (16000 * 2 bytes * 0.04)
READ_CHUNK = 1280

CARD_URL_BASE = "/resel_fxo_gateway"
CARD_FILENAME = "resel-intercom-card.js"

# Dispatcher signal sent when the options (card audio settings) change: f"{SIGNAL_SETTINGS}_{entry_id}"
SIGNAL_SETTINGS = f"{DOMAIN}_settings"

# ---------------------------------------------------------------- card audio settings (integration options)
# Edited in Settings -> Devices & services -> Resel FXO HA Gateway -> Configure, and pushed live to every
# open card. A value set in the card YAML still wins over the one stored here.
# Grouped in sections exactly as the options form shows them: {section: {key: default}}.
# gate_db is optional: empty = automatic threshold (follows the line noise floor).
SETTINGS_SECTIONS: dict[str, dict[str, object]] = {
    "talk": {
        "ptt_mode": "hold",
        "ptt_timeout": 30,
        "mic_gain": 1.0,
        "mic_echo_cancel": True,
        "mic_noise_suppress": True,
        "mic_auto_gain": True,
    },
    "line_filters": {
        "gain": 2.0,
        "highpass_hz": 250,
        "lowpass_hz": 3400,
        "notch_hz": 50,
        "notch_max_hz": 1500,
        "notch_q": 30,
    },
    "line_cleaning": {
        "denoise": True,
        "denoise_pregain_db": 0,
        "spectral_nr": False,
        "spectral_nr_strength": 3,
        "spectral_nr_floor_db": 18,
        "gate": True,
        "gate_margin_db": 10,
        "gate_db": None,
        "gate_floor_db": 24,
        "gate_hold_ms": 250,
        "leveler": False,
        "leveler_target_db": -24,
        "leveler_max_gain_db": 15,
    },
}

SETTINGS_DEFAULTS: dict[str, object] = {
    k: v for section in SETTINGS_SECTIONS.values() for k, v in section.items()
}
