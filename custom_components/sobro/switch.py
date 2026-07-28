"""Switch platform for Sobro Smart Furniture."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SobroConfigEntry
from .const import PROP_BLE_SWITCH, PROP_COOLING
from .coordinator import SobroCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SobroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[SwitchEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        data = coordinator.data
        if PROP_COOLING in data:
            entities.append(SobroCoolingSwitch(coordinator))
        if PROP_BLE_SWITCH in data:
            entities.append(SobroBleSwitch(coordinator))
    async_add_entities(entities)


class _SobroSwitch(CoordinatorEntity[SobroCoordinator], SwitchEntity):
    """Base class for simple boolean Sobro switches."""

    _attr_has_entity_name = True
    _prop_name: str  # Ayla property name, set by subclass

    def __init__(self, coordinator: SobroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        prop = self.coordinator.data.get(self._prop_name)
        if prop is None:
            return None
        return bool(prop.value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        prop = self.coordinator.data[self._prop_name]
        await self.coordinator.client.async_set_property(prop.property_id, 1)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        prop = self.coordinator.data[self._prop_name]
        await self.coordinator.client.async_set_property(prop.property_id, 0)
        await self.coordinator.async_request_refresh()


class SobroCoolingSwitch(_SobroSwitch):
    """Cooling / refrigeration compartment switch."""

    _prop_name = PROP_COOLING
    _attr_name = "Cooling"
    _attr_icon = "mdi:snowflake"

    def __init__(self, coordinator: SobroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dsn}_cooling"


class SobroBleSwitch(_SobroSwitch):
    """Bluetooth pairing-mode switch.

    Enabling this forces the device into BT pairing mode.
    """

    _prop_name = PROP_BLE_SWITCH
    _attr_name = "Bluetooth Pairing"
    _attr_icon = "mdi:bluetooth"

    def __init__(self, coordinator: SobroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dsn}_ble"
