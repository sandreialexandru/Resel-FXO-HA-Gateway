"""Config flow for the Resel FXO HA Gateway integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .bridge import validate_connection
from .const import CONF_HOST, CONF_PORT, CONF_TOKEN, DEFAULT_PORT, DOMAIN


class ReselFxoGatewayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

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
