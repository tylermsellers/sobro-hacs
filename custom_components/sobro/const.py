"""Constants for the Sobro integration."""

from __future__ import annotations

DOMAIN = "sobro"

# ── Config entry keys ─────────────────────────────────────────────────────────
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_APP_ID = "app_id"
CONF_APP_SECRET = "app_secret"
CONF_AUTH_URL = "auth_url"
CONF_ADS_URL = "ads_url"

# ── Ayla Networks default endpoints ──────────────────────────────────────────
# Override both to the same mock-server address when using local control.
DEFAULT_AUTH_URL = "https://user-field.aylanetworks.com"
DEFAULT_ADS_URL = "https://ads-field.aylanetworks.com"

# ── Ayla app credentials ──────────────────────────────────────────────────────
# These are the fixed client credentials the official Sobro mobile app embeds
# for every user — they are not per-account secrets. Confirmed via the JoeBro
# project's reverse engineering (github.com/nextgenredteam/joebro) and used
# here as the config flow defaults so most users never have to hunt for them
# with a MITM proxy. Still overridable in case StoreBound/Ayla ever rotates
# them or a different Sobro product line uses a different app_id.
DEFAULT_APP_ID = "sobro-ag-id"
DEFAULT_APP_SECRET = "sobro-mDM8M4JEe7IJFwiKvbs956XqX_s"

# ── Product identification & imagery ─────────────────────────────────────────
# Ayla's /apiv1/devices.json returns "product_name" / "oem_model" per device.
# Sobro currently sells two smart-furniture designs. We match on these fields
# (case-insensitively, best-effort — the exact values were never officially
# documented) to show a friendlier model name and, where confidently matched,
# a product photo entity.
#
# IMPORTANT: these photo URLs point directly at sobrodesign.com's own product
# pages. This repository does NOT download, store, or redistribute SOBRO's
# commercial product photography — the URL is only ever used as a plain
# ``entity_picture`` value, which the Home Assistant frontend renders as a
# browser-side hotlink (an <img src="..."> fetched by the user's own
# browser directly from sobrodesign.com). Do not switch this to the
# ``image`` platform / ImageEntity, which would make Home Assistant's own
# server download and cache a copy of the image — that crosses from linking
# into redistribution.
PRODUCT_MODEL_COFFEE_TABLE = "Smart Coffee Table"
PRODUCT_MODEL_SIDE_TABLE = "Smart Side Table"
PRODUCT_MODEL_UNKNOWN = "Smart Furniture"

PRODUCT_IMAGE_COFFEE_TABLE = (
    "https://sobrodesign.com/cdn/shop/products/Sobro_for_Amazon_White_1.jpg"
)
PRODUCT_IMAGE_SIDE_TABLE = "https://sobrodesign.com/cdn/shop/products/SOSTB300BKBK_2.jpg"


def guess_product(product_name: str | None, oem_model: str | None) -> tuple[str, str | None]:
    """Best-effort match of an Ayla device to a known Sobro model + photo URL.

    Falls back to a generic model name and no photo if neither field
    contains a recognisable keyword.
    """
    haystack = f"{product_name or ''} {oem_model or ''}".lower()
    if "coffee" in haystack:
        return PRODUCT_MODEL_COFFEE_TABLE, PRODUCT_IMAGE_COFFEE_TABLE
    if "side" in haystack:
        return PRODUCT_MODEL_SIDE_TABLE, PRODUCT_IMAGE_SIDE_TABLE
    return PRODUCT_MODEL_UNKNOWN, None


# ── Polling ───────────────────────────────────────────────────────────────────
SCAN_INTERVAL = 60  # seconds

# ── Ayla property names ───────────────────────────────────────────────────────
PROP_COOLING = "Cooling_switch"
PROP_DRAWER_LOCK = "Drawer_lock"
PROP_FRONT_KEY = "F_key"
PROP_BACK_KEY = "B_key"
PROP_BLE_SWITCH = "ble_switch"
PROP_BRIGHTNESS = "brightness"
PROP_FLIGHT_STATUS = "flight_status"
PROP_MODE_STATUS = "mode_status"
PROP_VERSION = "version"

# Properties surfaced only as diagnostic sensors
PROP_DIAGNOSTICS: frozenset[str] = frozenset(
    [
        "adjust_br",
        "Attribute",
        "custom_list",
        "disconnect_ble",
        "get_snapshot",
        "key",
        "main_list",
        PROP_VERSION,
    ]
)

# ── flight_status auto-brightness mode values ─────────────────────────────────
FLIGHT_AUTO_MANUAL = 0
FLIGHT_AUTO_MOTION = 5
FLIGHT_AUTO_NIGHTLIGHT = 6

# Ordered list used by the select entity.
FLIGHT_AUTO_MODE_OPTIONS = ["Manual", "Motion", "Nightlight"]
FLIGHT_AUTO_MODE_TO_VALUE: dict[str, int] = {
    "Manual": FLIGHT_AUTO_MANUAL,
    "Motion": FLIGHT_AUTO_MOTION,
    "Nightlight": FLIGHT_AUTO_NIGHTLIGHT,
}
FLIGHT_AUTO_VALUE_TO_MODE: dict[int, str] = {
    v: k for k, v in FLIGHT_AUTO_MODE_TO_VALUE.items()
}

# Front light color temperature range (Kelvin, confirmed on nightstand hardware)
FLIGHT_COLOR_TEMP_MIN_K = 2000
FLIGHT_COLOR_TEMP_MAX_K = 7000

# ── mode_status effect offsets ────────────────────────────────────────────────
# These are added as plain integers on top of the packed (G|B|R|0) value.
# See unpack_rgb / pack_rgb_effect below — do NOT try to bit-mask them out.
EFFECT_CONSTANT = 4
EFFECT_PULSE = 8
EFFECT_CYCLE = 12
EFFECT_RHYTHMIC = 16

# ── flight_status helpers ─────────────────────────────────────────────────────


def parse_flight_status(raw: str) -> dict[str, int]:
    """Parse "A:B:C:D" into named fields.

    A = auto-brightness mode (0=Manual, 5=Motion, 6=Nightlight)
    B = brightness (0-100)
    C = duration in seconds
    D = color temperature in Kelvin
    """
    parts = raw.split(":")
    return {
        "auto_mode": int(parts[0]),
        "brightness": int(parts[1]),
        "duration": int(parts[2]),
        "color_temp_k": int(parts[3]),
    }


def format_flight_status(
    auto_mode: int,
    brightness: int,
    duration: int,
    color_temp_k: int,
) -> str:
    """Rebuild the "A:B:C:D" string for a write.

    Always reconstruct the full string from current coordinator data —
    never write a partial value.
    """
    return f"{auto_mode}:{brightness}:{duration}:{color_temp_k}"


# ── mode_status helpers ───────────────────────────────────────────────────────


def unpack_rgb(value: int) -> tuple[int, int, int]:
    """Extract (R, G, B) from a packed mode_status integer."""
    value = int(value)
    r = (value >> 7) & 0xFF
    b = (value >> 15) & 0xFF
    g = (value >> 23) & 0xFF
    return r, g, b


def pack_rgb_effect(r: int, g: int, b: int, effect_offset: int = EFFECT_CONSTANT) -> int:
    """Pack (R, G, B) + effect offset into a mode_status integer.

    The effect offset is added as a plain integer on top of the bit-packed
    colour value, matching the firmware's own approach (empirically confirmed).
    """
    return ((g << 23) | (b << 15) | (r << 7)) + effect_offset
