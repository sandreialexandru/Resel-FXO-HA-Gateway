"""Config flow and options flow for the Resel FXO HA Gateway integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .bridge import validate_connection
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_TOKEN,
    DEFAULT_PORT,
    DOMAIN,
    SETTINGS_DEFAULTS,
    SETTINGS_SECTIONS,
)


def _num(min_: float, max_: float, step: float = 1, unit: str | None = None) -> NumberSelector:
    cfg = NumberSelectorConfig(min=min_, max=max_, step=step, mode=NumberSelectorMode.BOX)
    if unit:
        cfg["unit_of_measurement"] = unit
    return NumberSelector(cfg)


# Selector for every card setting (keys and defaults are in const.SETTINGS_SECTIONS).
SELECTORS: dict[str, Any] = {
    # talk
    "ptt_mode": SelectSelector(
        SelectSelectorConfig(options=["hold", "toggle"], mode=SelectSelectorMode.LIST, translation_key="ptt_mode")
    ),
    "ptt_timeout": _num(0, 600, 1, "s"),
    "mic_gain": _num(0, 20, 0.1, "x"),
    "mic_echo_cancel": BooleanSelector(),
    "mic_noise_suppress": BooleanSelector(),
    "mic_auto_gain": BooleanSelector(),
    # line filters
    "gain": _num(0, 20, 0.1, "x"),
    "highpass_hz": _num(0, 2000, 10, "Hz"),
    "lowpass_hz": _num(0, 8000, 50, "Hz"),
    "notch_hz": _num(0, 60, 10, "Hz"),
    "notch_max_hz": _num(0, 8000, 50, "Hz"),
    "notch_q": _num(1, 300, 1),
    # line cleaning
    "denoise": BooleanSelector(),
    "denoise_pregain_db": _num(0, 30, 1, "dB"),
    "gate": BooleanSelector(),
    "gate_margin_db": _num(0, 40, 1, "dB"),
    "gate_db": _num(-100, 0, 1, "dBFS"),
    "gate_floor_db": _num(0, 60, 1, "dB"),
    "gate_hold_ms": _num(0, 2000, 10, "ms"),
    "leveler": BooleanSelector(),
    "leveler_target_db": _num(-60, 0, 1, "dBFS"),
    "leveler_max_gain_db": _num(0, 40, 1, "dB"),
}


def card_settings(options: dict[str, Any]) -> dict[str, Any]:
    """Stored options merged over the defaults: the settings the card receives."""
    out = dict(SETTINGS_DEFAULTS)
    for key in SETTINGS_DEFAULTS:
        if key in options:
            out[key] = options[key]
    return out


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for sec_name, keys in SETTINGS_SECTIONS.items():
        sec_fields: dict[Any, Any] = {}
        for key in keys:
            value = current.get(key)
            if value is None:
                # optional field without a value (gate_db = automatic): leave the box empty
                sec_fields[vol.Optional(key)] = SELECTORS[key]
            else:
                sec_fields[vol.Optional(key, description={"suggested_value": value})] = SELECTORS[key]
        fields[vol.Required(sec_name)] = section(vol.Schema(sec_fields), {"collapsed": sec_name != "talk"})
    return vol.Schema(fields)


class ReselFxoGatewayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ReselFxoGatewayOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            token = user_input.get(CONF_TOKEN, "")
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()
            error = await validate_connection(host, user_input[CONF_PORT], token)
            if error is None:
                return self.async_create_entry(
                    title=f"Resel FXO gateway ({host})",
                    data={CONF_HOST: host, CONF_PORT: user_input[CONF_PORT], CONF_TOKEN: token},
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_TOKEN, default=(user_input or {}).get(CONF_TOKEN, "")): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class ReselFxoGatewayOptionsFlow(OptionsFlow):
    """Card audio settings: talk, line filters, line cleaning."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # sections arrive nested; store them flat. A key missing from the input was cleared in the
            # form: numbers fall back to their default, gate_db stays empty (= automatic threshold).
            flat: dict[str, Any] = {}
            for sec_name, keys in SETTINGS_SECTIONS.items():
                given = user_input.get(sec_name) or {}
                for key, default in keys.items():
                    value = given.get(key, default)
                    if isinstance(default, int) and not isinstance(default, bool) and value is not None:
                        value = int(value)
                    flat[key] = value
            return self.async_create_entry(data=flat)

        return self.async_show_form(
            step_id="init", data_schema=_options_schema(card_settings(dict(self.config_entry.options)))
        )
