"""Sensor platform for Sobro — diagnostic properties only."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SobroConfigEntry
from .const import DOMAIN, PROP_DIAGNOSTICS
from .coordinator import SobroCoordinator

_LOGGER = logging.getLogger(__name__)

# Only the properties in PROP_DIAGNOSTICS are surfaced; control properties
# are handled by their own dedicated platforms.
_DIAGNOSTIC_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    "version": SensorEntityDescription(
        key="version",
        name="Firmware Version",
        icon="mdi:tag-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "adjust_br": SensorEntityDescription(
        key="adjust_br",
        name="Adjust Brightness (raw)",
        icon="mdi:brightness-auto",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "Attribute": SensorEntityDescription(
        key="Attribute",
        name="Attribute (raw)",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "custom_list": SensorEntityDescription(
        key="custom_list",
        name="Custom List (raw)",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "disconnect_ble": SensorEntityDescription(
        key="disconnect_ble",
        name="Disconnect BLE (raw)",
        icon="mdi:bluetooth-off",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "get_snapshot": SensorEntityDescription(
        key="get_snapshot",
        name="Get Snapshot (raw)",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "key": SensorEntityDescription(
        key="key",
        name="Key (raw)",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "main_list": SensorEntityDescription(
        key="main_list",
        name="Main List (raw)",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SobroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[SensorEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for prop_name in PROP_DIAGNOSTICS:
            if prop_name in coordinator.data and prop_name in _DIAGNOSTIC_DESCRIPTIONS:
                entities.append(
                    SobroDiagnosticSensor(coordinator, _DIAGNOSTIC_DESCRIPTIONS[prop_name])
                )
    async_add_entities(entities)


class SobroDiagnosticSensor(CoordinatorEntity[SobroCoordinator], SensorEntity):
    """Read-only diagnostic sensor for a raw Ayla property."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SobroCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.dsn)},
            name=coordinator.device_name,
            manufacturer="Sobro",
            model="Smart Furniture",
        )

    @property
    def native_value(self) -> str | int | float | None:
        prop = self.coordinator.data.get(self.entity_description.key)
        return None if prop is None else prop.value
