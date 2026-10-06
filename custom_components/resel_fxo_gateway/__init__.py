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
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .bridge import AudioBridge, Listener
from .card_resource import async_register_card_resource, async_remove_card_resource, card_url
from .config_flow import card_settings
from .const import (
    CARD_URL_BASE,
    CONF_HOST,
    CONF_PORT,
    CONF_TOKEN,
    DOMAIN,
    SAMPLE_RATE,
    SIGNAL_SETTINGS,
)

_LOGGER = logging.getLogger(__name__)

MAX_SEND_BYTES = 16384  # sanity limit for one send_audio frame


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the card's JS file and the websocket commands (once)."""
    hass.data.setdefault(DOMAIN, {})
    frontend_dir = Path(__file__).parent / "frontend"
    # cache_headers=True lets the browser / companion app keep the card after the first download, so it is
    # available instantly when the app restarts (e.g. after switching from mobile data to Wi-Fi). Safe, because
    # the URL carries the version below: every release gets a new URL and is fetched again.
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, str(frontend_dir), cache_headers=True)]
        )
    except RuntimeError:
        _LOGGER.debug("Static path %s is already registered", CARD_URL_BASE)
    # the version in the URL makes browsers fetch the new card after every release
    version = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]
    # Main way: a Lovelace resource, loaded by the dashboard itself (works in browsers and in the companion app
    # even when they keep an old copy of the start page). Registered once Home Assistant has started.
    async def _register_resource(_hass: HomeAssistant) -> None:
        await async_register_card_resource(hass, version)

    async_at_started(hass, _register_resource)
    # Fallback: injected into the start page (same URL, so the browser runs the module only once).
    add_extra_js_url(hass, card_url(version))
    websocket_api.async_register_command(hass, ws_subscribe_audio)
    websocket_api.async_register_command(hass, ws_send_audio)
    websocket_api.async_register_command(hass, ws_subscribe_settings)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bridge = AudioBridge(entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data.get(CONF_TOKEN, ""))
    hass.data[DOMAIN][entry.entry_id] = bridge
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed: push the new card settings to every open card (no reload, the call keeps going)."""
    async_dispatcher_send(hass, f"{SIGNAL_SETTINGS}_{entry.entry_id}", card_settings(dict(entry.options)))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bridge: AudioBridge = hass.data[DOMAIN].pop(entry.entry_id)
    await bridge.async_close()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The last entry was deleted: take the card's Lovelace resource away too."""
    if not [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]:
        await async_remove_card_resource(hass)


def _get_bridge(hass: HomeAssistant) -> AudioBridge | None:
    bridges = hass.data.get(DOMAIN, {})
    return next(iter(bridges.values()), None) if bridges else None


def _get_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """The config entry whose bridge the card uses (the first loaded one)."""
    entry_ids = list(hass.data.get(DOMAIN, {}))
    return hass.config_entries.async_get_entry(entry_ids[0]) if entry_ids else None


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe_settings"})
@callback
def ws_subscribe_settings(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Card audio settings from the integration options. Sent once, then again on every change."""
    entry = _get_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_configured", "Resel FXO gateway is not configured")
        return
    msg_id = msg["id"]

    @callback
    def on_change(settings: dict) -> None:
        connection.send_message(websocket_api.event_message(msg_id, {"settings": settings}))

    connection.subscriptions[msg_id] = async_dispatcher_connect(
        hass, f"{SIGNAL_SETTINGS}_{entry.entry_id}", on_change
    )
    connection.send_result(msg_id)
    on_change(card_settings(dict(entry.options)))


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
