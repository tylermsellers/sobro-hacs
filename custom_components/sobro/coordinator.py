"""DataUpdateCoordinator for a single Sobro device (DSN)."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PropertyData, SobroApiClient, SobroApiError, SobroAuthError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class SobroCoordinator(DataUpdateCoordinator[dict[str, PropertyData]]):
    """Polls one Sobro device (identified by DSN) every SCAN_INTERVAL seconds.

    ``coordinator.data`` is a ``dict[property_name, PropertyData]`` so every
    platform entity can look up both the current value AND the property ID
    needed for writes without an extra API call.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: SobroApiClient,
        dsn: str,
        device_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{dsn}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
            # HA 2026: skip dispatch when data is unchanged between polls.
            always_update=False,
        )
        self.client = client
        self.dsn = dsn
        self.device_name = device_name

    async def _async_update_data(self) -> dict[str, PropertyData]:
        try:
            return await self.client.async_get_properties(self.dsn)
        except SobroAuthError as exc:
            raise UpdateFailed(f"Authentication error for {self.dsn}: {exc}") from exc
        except SobroApiError as exc:
            raise UpdateFailed(f"API error for {self.dsn}: {exc}") from exc
