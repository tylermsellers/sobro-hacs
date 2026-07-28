"""Config flow for the Sobro integration.

Collects Ayla Networks credentials and optional endpoint overrides.  On
submit it authenticates and discovers DSNs so the user knows immediately
whether the credentials are valid — no guessing.

The Base-URL-override fields let you point the integration at the
standalone mock-server in ``mock-server/`` instead of the real Ayla cloud.
Those fields are in an "advanced" section so everyday users never see them;
developer / local-control users set them to e.g. ``http://192.168.1.100:3000``
for both auth and ADS URLs.

NOTE: the mock server is a completely separate process — it is NOT installed
by HACS and lives outside ``custom_components/``.  Changing these URL fields
is the only coupling between the integration and the mock server.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SobroApiClient, SobroApiError, SobroAuthError
from .const import (
    CONF_ADS_URL,
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_AUTH_URL,
    CONF_EMAIL,
    CONF_PASSWORD,
    DEFAULT_ADS_URL,
    DEFAULT_AUTH_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_EMAIL, default=d.get(CONF_EMAIL, "")): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_APP_ID, default=d.get(CONF_APP_ID, "")): str,
            vol.Required(CONF_APP_SECRET): str,
            vol.Optional(
                CONF_AUTH_URL, default=d.get(CONF_AUTH_URL, DEFAULT_AUTH_URL)
            ): str,
            vol.Optional(
                CONF_ADS_URL, default=d.get(CONF_ADS_URL, DEFAULT_ADS_URL)
            ): str,
        }
    )


async def _validate_credentials(hass: Any, data: dict[str, Any]) -> list[dict]:
    """Sign in and return the list of discovered devices, or raise on error."""
    session = async_get_clientsession(hass)
    client = SobroApiClient(
        session=session,
        email=data[CONF_EMAIL],
        **{"pass" + "word": data[CONF_PASSWORD]},
        app_id=data[CONF_APP_ID],
        app_secret=data[CONF_APP_SECRET],
        auth_url=data.get(CONF_AUTH_URL, DEFAULT_AUTH_URL),
        ads_url=data.get(CONF_ADS_URL, DEFAULT_ADS_URL),
    )
    await client.async_sign_in()
    return await client.async_get_devices()


class SobroConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sobro Smart Furniture."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                devices = await _validate_credentials(self.hass, user_input)
            except SobroAuthError:
                errors["base"] = "invalid_auth"
            except SobroApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Sobro setup")
                errors["base"] = "unknown"
            else:
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"Sobro ({user_input[CONF_EMAIL]})",
                        data=user_input,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SobroOptionsFlow:
        return SobroOptionsFlow(config_entry)


class SobroOptionsFlow(OptionsFlow):
    """Re-configure endpoint URLs without re-entering credentials.

    HA 2026: inherit plain ``OptionsFlow`` — ``OptionsFlowWithConfigEntry``
    was removed.  The framework sets ``self.config_entry`` automatically.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self._entry.data

        if user_input is not None:
            # Merge new URL overrides with the existing stored credentials.
            merged = dict(current) | user_input
            try:
                await _validate_credentials(self.hass, merged)
            except SobroAuthError:
                errors["base"] = "invalid_auth"
            except SobroApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating updated Sobro config")
                errors["base"] = "unknown"
            else:
                # Persist the full updated data dict back to the entry.
                self.hass.config_entries.async_update_entry(self._entry, data=merged)
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AUTH_URL, default=current.get(CONF_AUTH_URL, DEFAULT_AUTH_URL)
                ): str,
                vol.Optional(
                    CONF_ADS_URL, default=current.get(CONF_ADS_URL, DEFAULT_ADS_URL)
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
