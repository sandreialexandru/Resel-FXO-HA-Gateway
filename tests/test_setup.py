"""Integration level: setting up registers the card, removing the last entry takes it away."""
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.resel_fxo_gateway.card_resource import CARD_PATH, card_url
from custom_components.resel_fxo_gateway.const import DOMAIN

import json
from pathlib import Path

VERSION = json.loads(
    (Path(__file__).parent.parent / "custom_components" / DOMAIN / "manifest.json").read_text()
)["version"]


def _cards(hass):
    return [i for i in hass.data["lovelace"].resources.async_items() if i["url"].split("?")[0] == CARD_PATH]


async def test_setup_registers_resource_and_remove_deletes_it(hass):
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "lovelace", {})
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.1", "port": 6054, "token": ""})
    entry.add_to_hass(hass)
    with patch("custom_components.resel_fxo_gateway.AudioBridge") as bridge_cls:
        bridge_cls.return_value = MagicMock(async_close=AsyncMock())
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        cards = _cards(hass)
        assert [c["url"] for c in cards] == [card_url(VERSION)]
        # Storage mode: the card must NOT also be injected into the start page (that early load races
        # with the scoped custom-element registry and makes the card intermittently missing)
        from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
        assert card_url(VERSION) not in hass.data[DATA_EXTRA_MODULE_URL].urls

        assert await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
        assert _cards(hass) == []


async def test_adding_the_gateway_back_registers_the_resource_again(hass):
    """Removing the last entry deletes the resource; async_setup does not run again, setup_entry must redo it."""
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "lovelace", {})
    with patch("custom_components.resel_fxo_gateway.AudioBridge") as bridge_cls:
        bridge_cls.return_value = MagicMock(async_close=AsyncMock())
        first = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.1", "port": 6054, "token": ""})
        first.add_to_hass(hass)
        assert await hass.config_entries.async_setup(first.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_remove(first.entry_id)
        await hass.async_block_till_done()
        assert _cards(hass) == []

        second = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.5", "port": 6054, "token": ""})
        second.add_to_hass(hass)
        assert await hass.config_entries.async_setup(second.entry_id)
        await hass.async_block_till_done()
        assert [c["url"] for c in _cards(hass)] == [card_url(VERSION)]
