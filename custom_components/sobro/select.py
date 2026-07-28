"""Select platform for Sobro — front-light auto-brightness mode."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SobroConfigEntry
from .const import (
    DOMAIN,
    FLIGHT_AUTO_MODE_OPTIONS,
    FLIGHT_AUTO_MODE_TO_VALUE,
    FLIGHT_AUTO_VALUE_TO_MODE,
    PROP_FLIGHT_STATUS,
    format_flight_status,
    parse_flight_status,
)
from .coordinator import SobroCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SobroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities = []
    for coordinator in entry.runtime_data.coordinators.values():
        if PROP_FLIGHT_STATUS in coordinator.data:
            entities.append(SobroFrontAutoMode(coordinator))
    async_add_entities(entities)


class SobroFrontAutoMode(CoordinatorEntity[SobroCoordinator], SelectEntity):
    """Front-light auto-brightness mode (field A of flight_status).

    Options:
    - **Manual** (0) — light stays at the brightness you set.
    - **Motion** (5) — light turns on when motion is detected.
    - **Nightlight** (6) — light turns on when darkness is detected.
    """

    _attr_has_entity_name = True
    _attr_name = "Front Light Auto Mode"
    _attr_options = FLIGHT_AUTO_MODE_OPTIONS
    _attr_icon = "mdi:auto-mode"

    def __init__(self, coordinator: SobroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dsn}_front_auto_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.dsn)},
            name=coordinator.device_name,
            manufacturer="Sobro",
            model="Smart Furniture",
        )

    @property
    def current_option(self) -> str | None:
        prop = self.coordinator.data.get(PROP_FLIGHT_STATUS)
        if prop is None or prop.value is None:
            return None
        try:
            fields = parse_flight_status(str(prop.value))
        except (ValueError, IndexError):
            return None
        return FLIGHT_AUTO_VALUE_TO_MODE.get(fields["auto_mode"])

    async def async_select_option(self, option: str) -> None:
        """Write a new auto mode via read-modify-write on flight_status."""
        new_mode_int = FLIGHT_AUTO_MODE_TO_VALUE.get(option)
        if new_mode_int is None:
            _LOGGER.error("Unknown Sobro auto mode: %r", option)
            return

        prop = self.coordinator.data[PROP_FLIGHT_STATUS]
        try:
            fields = parse_flight_status(str(prop.value))
        except (ValueError, IndexError):
            _LOGGER.error("Cannot parse flight_status: %r", prop.value)
            return

        new_raw = format_flight_status(
            new_mode_int,
            fields["brightness"],
            fields["duration"],
            fields["color_temp_k"],
        )
        await self.coordinator.client.async_set_property(prop.property_id, new_raw)
        await self.coordinator.async_request_refresh()
