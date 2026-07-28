"""DataUpdateCoordinator for a single Sobro device (DSN)."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PropertyData, SobroApiClient, SobroApiError, SobroAuthError
from .const import DOMAIN, PRODUCT_MODEL_UNKNOWN, SCAN_INTERVAL

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
        model: str = PRODUCT_MODEL_UNKNOWN,
        image_url: str | None = None,
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
        self.model = model
        # A URL on sobrodesign.com's own CDN, or None if the model couldn't be
        # confidently matched. See const.guess_product for details on why this
        # is only ever used as a hotlink, never downloaded into this repo.
        self.image_url = image_url

    @property
    def device_info(self) -> DeviceInfo:
        """Shared DeviceInfo for every entity belonging to this device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.dsn)},
            name=self.device_name,
            manufacturer="Sobro",
            model=self.model,
        )

    async def _async_update_data(self) -> dict[str, PropertyData]:
        try:
            return await self.client.async_get_properties(self.dsn)
        except SobroAuthError as exc:
            raise UpdateFailed(f"Authentication error for {self.dsn}: {exc}") from exc
        except SobroApiError as exc:
            raise UpdateFailed(f"API error for {self.dsn}: {exc}") from exc
