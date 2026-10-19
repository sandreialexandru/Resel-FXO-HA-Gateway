"""Config flow: adding the gateway and changing its address later (reconfigure)."""
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.resel_fxo_gateway.const import DOMAIN

VALIDATE = "custom_components.resel_fxo_gateway.config_flow.validate_connection"


def _entry(host="192.0.2.1"):
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=host.lower(),
        title=f"Resel FXO gateway ({host})",
        data={"host": host, "port": 6054, "token": "abc"},
    )


async def _start_reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def test_reconfigure_changes_the_host_and_keeps_the_entry(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.resel_fxo_gateway.AudioBridge") as bridge_cls, patch(VALIDATE, return_value=None):
        bridge_cls.return_value = MagicMock(async_close=AsyncMock())
        assert await hass.config_entries.async_setup(entry.entry_id)
        result = await _start_reconfigure(hass, entry)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"
        # the form is filled with the current values
        assert [str(k.default()) for k in result["data_schema"].schema if str(k) == "host"] == ["192.0.2.1"]

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.0.2.77", "port": 6054, "token": "abc"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "192.0.2.77"
    assert entry.unique_id == "192.0.2.77"
    assert entry.title == "Resel FXO gateway (192.0.2.77)"


async def test_reconfigure_shows_the_error_and_keeps_the_old_host(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)
    with patch(VALIDATE, return_value="cannot_connect"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.0.2.99", "port": 6054, "token": "abc"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data["host"] == "192.0.2.1"


async def test_reconfigure_refuses_the_address_of_another_gateway(hass):
    entry = _entry("192.0.2.1")
    other = _entry("192.0.2.2")
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)
    with patch(VALIDATE, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.0.2.2", "port": 6054, "token": ""}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "192.0.2.1"
