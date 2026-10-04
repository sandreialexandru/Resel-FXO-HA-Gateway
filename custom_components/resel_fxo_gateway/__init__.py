"""Resel FXO HA Gateway: voice bridge between a Lovelace card and the ESP32 audio_tcp port."""
from __future__ import annotations

import base64
import binascii
import json
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType

from .bridge import AudioBridge, Listener
from .const import (
    CARD_FILENAME,
    CARD_URL_BASE,
    CONF_HOST,
    CONF_PORT,
    CONF_TOKEN,
    DOMAIN,
    SAMPLE_RATE,
)

_LOGGER = logging.getLogger(__name__)

MAX_SEND_BYTES = 16384  # sanity limit for one send_audio frame


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the card's JS file and the websocket commands (once)."""
    hass.data.setdefault(DOMAIN, {})
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_BASE, str(frontend_dir), cache_headers=False)]
    )
    # the version in the URL makes browsers fetch the new card after every release
    version = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]
    add_extra_js_url(hass, f"{CARD_URL_BASE}/{CARD_FILENAME}?v={version}")
    websocket_api.async_register_command(hass, ws_subscribe_audio)
    websocket_api.async_register_command(hass, ws_send_audio)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bridge = AudioBridge(entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data.get(CONF_TOKEN, ""))
    hass.data[DOMAIN][entry.entry_id] = bridge
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bridge: AudioBridge = hass.data[DOMAIN].pop(entry.entry_id)
    await bridge.async_close()
    return True


def _get_bridge(hass: HomeAssistant) -> AudioBridge | None:
    bridges = hass.data.get(DOMAIN, {})
    return next(iter(bridges.values()), None) if bridges else None


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe_audio"})
@websocket_api.require_admin
@callback
def ws_subscribe_audio(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Stream audio from the ESP32 to the card. Events: status / audio (base64 PCM)."""
    bridge = _get_bridge(hass)
    if bridge is None:
        connection.send_error(msg["id"], "not_configured", "Resel FXO gateway is not configured")
        return
    msg_id = msg["id"]

    @callback
    def on_audio(data: bytes) -> None:
        connection.send_message(
            websocket_api.event_message(
                msg_id, {"type": "audio", "data": base64.b64encode(data).decode("ascii")}
            )
        )

    @callback
    def on_status(connected: bool) -> None:
        connection.send_message(websocket_api.event_message(msg_id, {"type": "status", "connected": connected}))

    listener = Listener(on_audio=on_audio, on_status=on_status)

    @callback
    def unsub() -> None:
        bridge.remove_listener(listener)

    connection.subscriptions[msg_id] = unsub
    connection.send_result(msg_id, {"sample_rate": SAMPLE_RATE, "format": "pcm_s16le_mono"})
    bridge.add_listener(listener)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/send_audio", vol.Required("data"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_send_audio(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Send base64 PCM (16 kHz, s16le, mono) from the card to the ESP32 speaker."""
    bridge = _get_bridge(hass)
    if bridge is None:
        connection.send_error(msg["id"], "not_configured", "Resel FXO gateway is not configured")
        return
    try:
        pcm = base64.b64decode(msg["data"], validate=True)
    except (binascii.Error, ValueError):
        connection.send_error(msg["id"], "invalid_format", "data is not valid base64")
        return
    if len(pcm) > MAX_SEND_BYTES:
        connection.send_error(msg["id"], "too_large", "audio frame too large")
        return
    await bridge.send(pcm)
    connection.send_result(msg["id"])
