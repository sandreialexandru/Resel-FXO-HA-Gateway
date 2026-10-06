"""The card must be a single, up-to-date Lovelace resource (storage mode)."""
from homeassistant.setup import async_setup_component

from custom_components.resel_fxo_gateway.card_resource import (
    CARD_PATH,
    async_register_card_resource,
    async_remove_card_resource,
    card_url,
)


async def _lovelace(hass):
    assert await async_setup_component(hass, "lovelace", {})
    await hass.async_block_till_done()
    return hass.data["lovelace"].resources


def _cards(resources):
    return [i for i in resources.async_items() if i["url"].split("?")[0] == CARD_PATH]


async def test_register_twice_gives_one_resource(hass):
    resources = await _lovelace(hass)
    assert await async_register_card_resource(hass, "1.0.0")
    assert await async_register_card_resource(hass, "1.0.0")
    cards = _cards(resources)
    assert len(cards) == 1
    assert cards[0]["url"] == card_url("1.0.0")
    assert cards[0]["type"] == "module"


async def test_new_version_updates_instead_of_duplicating(hass):
    resources = await _lovelace(hass)
    await async_register_card_resource(hass, "1.0.0")
    first_id = _cards(resources)[0]["id"]
    await async_register_card_resource(hass, "1.1.0")
    cards = _cards(resources)
    assert len(cards) == 1
    assert cards[0]["id"] == first_id
    assert cards[0]["url"] == card_url("1.1.0")


async def test_duplicates_are_removed_and_other_resources_kept(hass):
    resources = await _lovelace(hass)
    await resources.async_load()
    resources.loaded = True
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_PATH}?v=0.1"})
    await resources.async_create_item({"res_type": "module", "url": CARD_PATH})
    await resources.async_create_item({"res_type": "module", "url": "/local/other-card.js"})
    await async_register_card_resource(hass, "2.0.0")
    cards = _cards(resources)
    assert [c["url"] for c in cards] == [card_url("2.0.0")]
    assert any(i["url"] == "/local/other-card.js" for i in resources.async_items())


async def test_not_loaded_collection_is_loaded_first(hass, hass_storage):
    hass_storage["lovelace_resources"] = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace_resources",
        "data": {"items": [{"id": "abc", "type": "module", "url": "/local/old.js"}]},
    }
    resources = await _lovelace(hass)
    assert resources.loaded is False
    await async_register_card_resource(hass, "1.0.0")
    assert resources.loaded is True
    urls = {i["url"] for i in resources.async_items()}
    assert urls == {"/local/old.js", card_url("1.0.0")}


async def test_remove(hass):
    resources = await _lovelace(hass)
    await async_register_card_resource(hass, "1.0.0")
    await async_remove_card_resource(hass)
    assert _cards(resources) == []


async def test_yaml_mode_only_logs(hass, caplog):
    assert await async_setup_component(
        hass, "lovelace", {"lovelace": {"mode": "yaml", "resources": []}}
    )
    await hass.async_block_till_done()
    assert await async_register_card_resource(hass, "1.0.0") is False
    assert "YAML mode" in caplog.text


async def test_without_lovelace_does_not_raise(hass):
    assert await async_register_card_resource(hass, "1.0.0") is False
