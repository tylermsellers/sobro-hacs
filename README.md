# Sobro Smart Furniture — Home Assistant Integration

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant integration for Sobro Smart Furniture (nightstands, coffee
tables).  Uses the Ayla Networks cloud API — the same API the Sobro mobile
app uses.

---

## Credit / Origin

This project is a **Home Assistant / HACS-focused fork** of
[**JoeBro**](https://github.com/nextgenredteam/joebro) by **Joe Brinkley**
([NextGenRedTeam](https://nextgenredteam.com/)). All of the Ayla Networks
API reverse-engineering this integration relies on — endpoint shapes, the
property map (`Cooling_switch`, `Drawer_lock`, `F_key`, `B_key`,
`ble_switch`, `brightness`, `flight_status`, `mode_status`), the
`mode_status` RGB bit-packing scheme, and the app's client credentials —
originates from that project and its accompanying write-up, [Rescuing
Abandoned IoT: the JoeBro Sobro Table
Rescue](https://nextgenredteam.com/blog/rescuing-abandoned-iot-joebro-sobro.html).

JoeBro itself is a standalone browser-based PWA controller plus a
Docker/Pi-hole based local mock API. This repository re-implements that same
reverse-engineered protocol as a native Home Assistant custom component so
Sobro devices can be managed through HA instead of (or alongside) the
Sobro devices can be managed through HA instead of (or alongside) the
JoeBro PWA. All credit for discovering how the Sobro/Ayla API works belongs
to Joe Brinkley and the JoeBro project — please go star/support the
[original repository](https://github.com/nextgenredteam/joebro).

---

## Repository layout

```
sobro-hacs/
  custom_components/
    sobro/               ← HACS installs ONLY this directory
      __init__.py
      manifest.json
      config_flow.py
      const.py
      coordinator.py
      api.py
      light.py           front + back light entities
      switch.py          cooling, BLE pairing
      lock.py            drawer lock
      number.py          front-light auto-off duration
      select.py          front-light auto mode
      sensor.py          diagnostic properties
      translations/
        en.json
  hacs.json
  README.md
```

---

## Installing via HACS

1. In Home Assistant, open **HACS → Integrations**.
2. Click the three-dot menu → **Custom repositories**.
3. Add `https://github.com/tylermsellers/sobro-hacs` as type **Integration**.
4. Search for "Sobro" and click **Download**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & Services → Add Integration → Sobro**.

---

## Configuration

The config flow collects:


| Field | Description |
|-------|-------------|
| **Email** | Ayla Networks account email (same as Sobro app) |
| **Password** | Ayla Networks account password |
| **App ID** | Client app ID — pre-filled with the known Sobro value, see below |
| **App Secret** | Client app secret — pre-filled with the known Sobro value, see below |
| **Auth Base URL** *(advanced)* | Default: `https://user-field.aylanetworks.com` |
| **ADS Base URL** *(advanced)* | Default: `https://ads-field.aylanetworks.com` |

On submit, the integration signs in and auto-discovers all Sobro devices
on your account.  Each device (DSN) appears as a separate HA device.

### App ID and App Secret

The Sobro mobile app embeds a single fixed `app_id`/`app_secret` pair that
is the same for every user (it is not a per-account secret) — the
[JoeBro project](https://github.com/nextgenredteam/joebro) reverse-engineered
and published these values, and the config flow pre-fills them for you
(`custom_components/sobro/const.py` → `DEFAULT_APP_ID` /
`DEFAULT_APP_SECRET`), so most users never need to touch these fields.

If Ayla/StoreBound ever rotates them, you can still capture new values with
[HTTP Toolkit](https://httptoolkit.com/) or a similar MITM proxy while using
the official Sobro app, and enter them manually in the config flow.

---

## Entities per device

| Entity | Platform | Ayla property |
|--------|----------|---------------|
| Front Light | `light` | `F_key` + `flight_status` |
| Back Light | `light` | `B_key` + `brightness` + `mode_status` |
| Cooling | `switch` | `Cooling_switch` |
| Bluetooth Pairing | `switch` | `ble_switch` |
| Drawer | `lock` | `Drawer_lock` |
| Front Light Duration | `number` | `flight_status` field C |
| Front Light Auto Mode | `select` | `flight_status` field A |
| Firmware Version | `sensor` | `version` (diagnostic) |
| Product Model | `sensor` | derived from `product_name`/`oem_model` (diagnostic) |
| *(other raw props)* | `sensor` | various (diagnostic, disabled by default) |

### Device images

Each device is created with a `model` (e.g. "Smart Coffee Table" or "Smart
Side Table") matched from the Ayla API's `product_name`/`oem_model` fields —
this is what Home Assistant shows on the device page instead of a generic
"Smart Furniture" placeholder.

When a model is confidently matched, a diagnostic **Product Model** sensor
is also created with its `entity_picture` pointing directly at that
product's photo on `sobrodesign.com`. This is a plain hotlink — the Home
Assistant frontend fetches the image straight from SOBRO's own server in
the user's browser. This repository does not download, cache, or
redistribute a copy of SOBRO's product photography anywhere.

There is currently no icon/logo for this integration in the community
[`home-assistant/brands`](https://github.com/home-assistant/brands) repo,
but that's no longer needed: as of Home Assistant 2026.3, integrations can
ship their own brand images locally. This repo includes a simple, original
(non-trademarked) icon at `custom_components/sobro/brand/icon.png` /
`icon@2x.png` — a minimalist table-with-glowing-light glyph — shown on the
Integrations page and device pages on HA 2026.3+. Older HA versions will
still show a generic placeholder there.

### flight_status format

`"A:B:C:D"` — **always read-modify-write; never write a partial string.**

| Field | Meaning | Values |
|-------|---------|--------|
| A | Auto-brightness mode | 0=Manual, 5=Motion, 6=Nightlight |
| B | Brightness | 0–100 |
| C | Auto-off duration (seconds) | 0–86400 |
| D | Colour temperature (Kelvin) | ~2000–7000 |

### mode_status RGB packing

```python
packed = ((G << 23) | (B << 15) | (R << 7)) + effect_offset
# effect_offset: Constant=4, Pulse=8, Cycle=12, Rhythmic=16
```

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `invalid_auth` on setup | Wrong App ID / App Secret |
| `cannot_connect` on setup | Auth Base URL unreachable; check network |
| No devices found | Wrong ADS Base URL, or account has no registered devices |
| Entity shows unavailable | Device offline or polling error — check HA logs |
| Write has no effect | Confirm property ID via `GET /apiv1/dsns/<dsn>/properties.json` |
| Ayla returns 404 on write | Property ID may differ per unit — re-discover via properties.json |

---

## Architecture notes

- **One config entry = one Ayla account.** Multiple devices (DSNs) on the
  same account are represented as separate HA devices under the same entry.
- **Tokens are held in memory.** If HA restarts, the client re-authenticates
  automatically from stored credentials.
- **`iot_class: cloud_polling`** because HA has no better-matching class for
  this integration's polling-based cloud API.  Document caveat, don't fight the field.
- **No `requests` dependency.** All network I/O uses `aiohttp` via HA's own
  session manager — synchronous calls would block the HA event loop.

---

## License

MIT — see [LICENSE](LICENSE). This project is a derivative of
[JoeBro](https://github.com/nextgenredteam/joebro) by Joe Brinkley /
NextGenRedTeam; please credit and support the original project.

