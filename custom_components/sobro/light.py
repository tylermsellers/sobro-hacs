"""Light platform for Sobro Smart Furniture.

Two light entities per device:
- **Front light** — controlled by ``F_key`` (on/off) and ``flight_status``
  (brightness, colour temperature, auto mode, duration).
  Uses ``ColorMode.COLOR_TEMP`` with a 2 000–7 000 K range.

- **Back light** — controlled by ``B_key`` (on/off), ``brightness`` (0–100),
  and ``mode_status`` (packed RGB + effect).
  Uses ``ColorMode.HS``; HA converts between HS and RGB automatically.

All writes to ``flight_status`` are **read-modify-write**: the current value
is read from the coordinator, the relevant field mutated, and the full
"A:B:C:D" string written back.  Never write a partial string.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.color import color_hs_to_RGB, color_RGB_to_hs

from . import SobroConfigEntry
from .api import PropertyData
from .const import (
    FLIGHT_COLOR_TEMP_MAX_K,
    FLIGHT_COLOR_TEMP_MIN_K,
    PROP_BACK_KEY,
    PROP_BRIGHTNESS,
    PROP_FLIGHT_STATUS,
    PROP_FRONT_KEY,
    PROP_MODE_STATUS,
    EFFECT_CONSTANT,
    format_flight_status,
    pack_rgb_effect,
    parse_flight_status,
    unpack_rgb,
)
from .coordinator import SobroCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SobroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[LightEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        data = coordinator.data
        if PROP_FRONT_KEY in data and PROP_FLIGHT_STATUS in data:
            entities.append(SobroFrontLight(coordinator))
        if PROP_BACK_KEY in data and PROP_BRIGHTNESS in data and PROP_MODE_STATUS in data:
            entities.append(SobroBackLight(coordinator))
    async_add_entities(entities)


class SobroFrontLight(CoordinatorEntity[SobroCoordinator], LightEntity):
    """Front under-cabinet / ambient light.

    Properties used:
    - ``F_key`` — on/off boolean
    - ``flight_status`` — "autoMode:brightness:duration:colorTempK"
    """

    _attr_has_entity_name = True
    _attr_name = "Front Light"
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_min_color_temp_kelvin = FLIGHT_COLOR_TEMP_MIN_K
    _attr_max_color_temp_kelvin = FLIGHT_COLOR_TEMP_MAX_K

    def __init__(self, coordinator: SobroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dsn}_front_light"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        prop = self.coordinator.data.get(PROP_FRONT_KEY)
        if prop is None:
            return None
        return bool(prop.value)

    @property
    def brightness(self) -> int | None:
        flight = self._flight_fields()
        if flight is None:
            return None
        # HA brightness is 0–255; flight_status brightness is 0–100.
        return round(flight["brightness"] / 100 * 255)

    @property
    def color_temp_kelvin(self) -> int | None:
        flight = self._flight_fields()
        return flight["color_temp_k"] if flight else None

    def _flight_fields(self) -> dict | None:
        prop = self.coordinator.data.get(PROP_FLIGHT_STATUS)
        if prop is None or prop.value is None:
            return None
        try:
            return parse_flight_status(str(prop.value))
        except (ValueError, IndexError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        data = self.coordinator.data

        # Turn on via F_key.
        await client.async_set_property(data[PROP_FRONT_KEY].property_id, 1)

        # If brightness or colour temp was also requested, apply via
        # read-modify-write on flight_status.
        if ATTR_BRIGHTNESS in kwargs or ATTR_COLOR_TEMP_KELVIN in kwargs:
            flight = self._flight_fields() or {
                "auto_mode": 0, "brightness": 50, "duration": 60, "color_temp_k": 4000
            }
            if ATTR_BRIGHTNESS in kwargs:
                ha_bri = kwargs[ATTR_BRIGHTNESS]
                flight["brightness"] = round(ha_bri / 255 * 100)
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                flight["color_temp_k"] = kwargs[ATTR_COLOR_TEMP_KELVIN]

            new_value = format_flight_status(
                flight["auto_mode"],
                flight["brightness"],
                flight["duration"],
                flight["color_temp_k"],
            )
            await client.async_set_property(data[PROP_FLIGHT_STATUS].property_id, new_value)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_set_property(
            self.coordinator.data[PROP_FRONT_KEY].property_id, 0
        )
        await self.coordinator.async_request_refresh()


class SobroBackLight(CoordinatorEntity[SobroCoordinator], LightEntity):
    """Back RGB accent light.

    Properties used:
    - ``B_key`` — on/off boolean
    - ``brightness`` — integer 0–100
    - ``mode_status`` — packed (G<<23)|(B<<15)|(R<<7) + effect offset
    """

    _attr_has_entity_name = True
    _attr_name = "Back Light"
    _attr_supported_color_modes = {ColorMode.HS}
    _attr_color_mode = ColorMode.HS

    def __init__(self, coordinator: SobroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dsn}_back_light"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        prop = self.coordinator.data.get(PROP_BACK_KEY)
        if prop is None:
            return None
        return bool(prop.value)

    @property
    def brightness(self) -> int | None:
        prop = self.coordinator.data.get(PROP_BRIGHTNESS)
        if prop is None or prop.value is None:
            return None
        return round(int(prop.value) / 100 * 255)

    @property
    def hs_color(self) -> tuple[float, float] | None:
        prop = self.coordinator.data.get(PROP_MODE_STATUS)
        if prop is None or prop.value is None:
            return None
        r, g, b = unpack_rgb(prop.value)
        return color_RGB_to_hs(r, g, b)

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        data = self.coordinator.data

        await client.async_set_property(data[PROP_BACK_KEY].property_id, 1)

        if ATTR_BRIGHTNESS in kwargs:
            ha_bri = kwargs[ATTR_BRIGHTNESS]
            device_bri = round(ha_bri / 255 * 100)
            await client.async_set_property(data[PROP_BRIGHTNESS].property_id, device_bri)

        if ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            r, g, b = color_hs_to_RGB(h, s)
            packed = pack_rgb_effect(r, g, b, EFFECT_CONSTANT)
            await client.async_set_property(data[PROP_MODE_STATUS].property_id, packed)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_set_property(
            self.coordinator.data[PROP_BACK_KEY].property_id, 0
        )
        await self.coordinator.async_request_refresh()
