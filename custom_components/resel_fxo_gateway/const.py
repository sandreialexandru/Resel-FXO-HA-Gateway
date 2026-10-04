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
