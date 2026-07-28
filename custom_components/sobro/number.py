"""Number platform for Sobro — front-light auto-off duration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SobroConfigEntry
from .const import DOMAIN, PROP_FLIGHT_STATUS, format_flight_status, parse_flight_status
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
            entities.append(SobroFrontDuration(coordinator))
    async_add_entities(entities)


class SobroFrontDuration(CoordinatorEntity[SobroCoordinator], NumberEntity):
    """Front-light auto-off duration (field C of flight_status).

    This is the number of seconds the light stays on after a motion or
    darkness trigger before shutting off automatically.  It has no effect
    when the front light is in Manual mode.
    """

    _attr_has_entity_name = True
    _attr_name = "Front Light Duration"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 86400  # 24 h upper bound
    _attr_native_step = 1
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: SobroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dsn}_front_duration"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.dsn)},
            name=coordinator.device_name,
            manufacturer="Sobro",
            model="Smart Furniture",
        )

    @property
    def native_value(self) -> float | None:
        prop = self.coordinator.data.get(PROP_FLIGHT_STATUS)
        if prop is None or prop.value is None:
            return None
        try:
            return float(parse_flight_status(str(prop.value))["duration"])
        except (ValueError, IndexError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Write a new duration via read-modify-write on flight_status."""
        prop = self.coordinator.data[PROP_FLIGHT_STATUS]
        try:
            fields = parse_flight_status(str(prop.value))
        except (ValueError, IndexError):
            _LOGGER.error("Cannot parse flight_status: %r", prop.value)
            return

        new_raw = format_flight_status(
            fields["auto_mode"],
            fields["brightness"],
            int(value),
            fields["color_temp_k"],
        )
        await self.coordinator.client.async_set_property(prop.property_id, new_raw)
        await self.coordinator.async_request_refresh()
