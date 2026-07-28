"""Lock platform for Sobro Smart Furniture — drawer lock."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SobroConfigEntry
from .const import DOMAIN, PROP_DRAWER_LOCK
from .coordinator import SobroCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SobroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities = []
    for coordinator in entry.runtime_data.coordinators.values():
        if PROP_DRAWER_LOCK in coordinator.data:
            entities.append(SobroDrawerLock(coordinator))
    async_add_entities(entities)


class SobroDrawerLock(CoordinatorEntity[SobroCoordinator], LockEntity):
    """Drawer lock.

    Ayla value: 1 = locked, 0 = unlocked.
    Verify against real hardware — the brief flags this mapping as needing
    confirmation on physical units.
    """

    _attr_has_entity_name = True
    _attr_name = "Drawer"

    def __init__(self, coordinator: SobroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dsn}_drawer_lock"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.dsn)},
            name=coordinator.device_name,
            manufacturer="Sobro",
            model="Smart Furniture",
        )

    @property
    def is_locked(self) -> bool | None:
        prop = self.coordinator.data.get(PROP_DRAWER_LOCK)
        if prop is None:
            return None
        return bool(prop.value)

    async def async_lock(self, **kwargs: Any) -> None:
        prop = self.coordinator.data[PROP_DRAWER_LOCK]
        await self.coordinator.client.async_set_property(prop.property_id, 1)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        prop = self.coordinator.data[PROP_DRAWER_LOCK]
        await self.coordinator.client.async_set_property(prop.property_id, 0)
        await self.coordinator.async_request_refresh()
