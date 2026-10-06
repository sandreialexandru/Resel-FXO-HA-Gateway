"""Keep the card registered as a Lovelace resource (so it loads in every browser and in the companion app).

`frontend.add_extra_js_url` only injects the script into the HTML of the start page. Browsers and the
companion app cache that page, so when it is older than the card registration (after a restart, an update or
an expired cache) the script is not loaded: "Custom element doesn't exist". A Lovelace resource is loaded by
the dashboard itself, from the resource list the frontend downloads over the websocket, so it does not
depend on the cached page. `add_extra_js_url` is still kept as a fallback (same URL: the browser runs the
module once).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CARD_FILENAME, CARD_URL_BASE, DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_PATH = f"{CARD_URL_BASE}/{CARD_FILENAME}"
_LOCK_KEY = f"{DOMAIN}_card_resource_lock"


def card_url(version: str) -> str:
    """The versioned URL: a new version gives a new URL, so the cache is emptied on every update."""
    return f"{CARD_PATH}?v={version}"


def _resources(hass: HomeAssistant) -> Any | None:
    """The Lovelace resource collection (LovelaceData object in recent HA, a dict in older versions)."""
    data = hass.data.get("lovelace")
    if data is None:
        return None
    if isinstance(data, dict):
        return data.get("resources")
    return getattr(data, "resources", None)


def _is_card(item: dict) -> bool:
    """True for a resource that points to our card, with or without a ?v= query."""
    return str(item.get("url", "")).split("?", 1)[0] == CARD_PATH


async def async_register_card_resource(hass: HomeAssistant, version: str) -> bool:
    """Create or update the Lovelace resource of the card. Returns True when the resource is in place."""
    lock = hass.data.setdefault(_LOCK_KEY, asyncio.Lock())
    async with lock:
        try:
            return await _async_register(hass, version)
        except Exception:  # noqa: BLE001 - never break the setup because of the resource
            _LOGGER.exception("Could not register the card as a Lovelace resource; add it manually: %s", card_url(version))
            return False


async def _async_register(hass: HomeAssistant, version: str) -> bool:
    resources = _resources(hass)
    url = card_url(version)
    if resources is None:
        _LOGGER.warning("Lovelace is not available; add the card resource manually: %s (type: JavaScript module)", url)
        return False
    if not hasattr(resources, "async_create_item"):
        # YAML mode: the resources are defined in configuration.yaml, Home Assistant cannot edit them
        _LOGGER.warning(
            "Lovelace is in YAML mode. Add this to your lovelace resources: "
            "{url: %s, type: module}",
            url,
        )
        return False

    if not getattr(resources, "loaded", True):
        await resources.async_load()
        resources.loaded = True

    ours = [item for item in resources.async_items() if _is_card(item)]
    if not ours:
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Registered the card as a Lovelace resource: %s", url)
        return True

    keep, duplicates = ours[0], ours[1:]
    if keep.get("url") != url or keep.get("type") != "module":
        await resources.async_update_item(keep["id"], {"res_type": "module", "url": url})
        _LOGGER.info("Updated the Lovelace resource of the card: %s", url)
    for item in duplicates:
        await resources.async_delete_item(item["id"])
        _LOGGER.info("Removed a duplicate Lovelace resource of the card: %s", item.get("url"))
    return True


async def async_remove_card_resource(hass: HomeAssistant) -> None:
    """Delete the card's Lovelace resource (called when the last config entry is removed)."""
    resources = _resources(hass)
    if resources is None or not hasattr(resources, "async_delete_item"):
        return
    lock = hass.data.setdefault(_LOCK_KEY, asyncio.Lock())
    async with lock:
        try:
            if not getattr(resources, "loaded", True):
                await resources.async_load()
                resources.loaded = True
            for item in [i for i in resources.async_items() if _is_card(i)]:
                await resources.async_delete_item(item["id"])
                _LOGGER.info("Removed the card's Lovelace resource: %s", item.get("url"))
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not remove the card's Lovelace resource")
