"""Sobro Smart Furniture — Home Assistant integration.

Architecture
------------
One config entry covers one Ayla Networks account (email + credentials).
On setup, the entry:
  1. Creates a shared ``SobroApiClient`` (handles auth & token refresh).
  2. Signs in and discovers all Sobro DSNs via ``/apiv1/devices.json``.
  3. Creates one ``SobroCoordinator`` per DSN (polls ``properties.json``).
  4. Stores everything in ``entry.runtime_data`` (HA 2026 typed pattern).
  5. Forwards to all platforms; each platform creates entities per coordinator.

The ``mock-server/`` directory in this repository contains a standalone
Node.js development server that impersonates the Ayla API.  It is NOT part
of this package and is never installed by HACS — see README § Local mock
server for how to run it alongside the integration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
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
from .coordinator import SobroCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


@dataclass
class SobroRuntimeData:
    """All runtime objects stored on the config entry."""

    client: SobroApiClient
    # DSN → coordinator; one coordinator per physical device on the account.
    coordinators: dict[str, SobroCoordinator] = field(default_factory=dict)


# HA 2026: generic ConfigEntry annotated with our runtime data type.
type SobroConfigEntry = ConfigEntry[SobroRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SobroConfigEntry) -> bool:
    """Set up all Sobro devices for this account config entry."""
    session = async_get_clientsession(hass)
    client = SobroApiClient(
        session=session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        app_id=entry.data[CONF_APP_ID],
        app_secret=entry.data[CONF_APP_SECRET],
        auth_url=entry.data.get(CONF_AUTH_URL, DEFAULT_AUTH_URL),
        ads_url=entry.data.get(CONF_ADS_URL, DEFAULT_ADS_URL),
    )

    try:
        await client.async_sign_in()
    except SobroAuthError as exc:
        raise ConfigEntryAuthFailed(f"Invalid credentials: {exc}") from exc
    except SobroApiError as exc:
        raise ConfigEntryNotReady(f"Could not reach Ayla API: {exc}") from exc

    try:
        devices = await client.async_get_devices()
    except SobroApiError as exc:
        raise ConfigEntryNotReady(f"Device discovery failed: {exc}") from exc

    if not devices:
        _LOGGER.error("No Sobro devices found on this account")
        raise ConfigEntryNotReady("No devices returned by Ayla API")

    runtime = SobroRuntimeData(client=client)

    for device in devices:
        dsn: str = device.get("dsn", "")
        if not dsn:
            continue
        name: str = device.get("product_name") or device.get("device_name") or f"Sobro {dsn}"
        coordinator = SobroCoordinator(hass, client, dsn, name)
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception:
            _LOGGER.warning("Sobro: could not fetch initial properties for %s", dsn)
            continue
        runtime.coordinators[dsn] = coordinator
        _LOGGER.debug("Sobro: registered device %s (%s)", dsn, name)

    if not runtime.coordinators:
        raise ConfigEntryNotReady("No devices could be initialised")

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SobroConfigEntry) -> bool:
    """Unload all platforms for this config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: SobroConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
