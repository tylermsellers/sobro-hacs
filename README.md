# Sobro Smart Furniture — Home Assistant Integration

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Home Assistant integration for Sobro Smart Furniture (nightstands, coffee
tables).  Uses the Ayla Networks cloud API — the same API the Sobro mobile
app uses.

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
  mock-server/           ← standalone dev server — NOT installed by HACS
    server.js
    Dockerfile
    docker-compose.yml
    README.md
  hacs.json
  README.md
```

> **Important:** `mock-server/` is a completely separate piece.  HACS's
> custom-repository flow only looks at `custom_components/sobro/manifest.json`
> — the mock server directory has no effect on installation.

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
| **App ID** | Client app ID (see *Obtaining credentials* below) |
| **App Secret** | Client app secret |
| **Auth Base URL** *(advanced)* | Default: `https://user-field.aylanetworks.com` |
| **ADS Base URL** *(advanced)* | Default: `https://ads-field.aylanetworks.com` |

On submit, the integration signs in and auto-discovers all Sobro devices
on your account.  Each device (DSN) appears as a separate HA device.

### Obtaining App ID and App Secret

The Sobro mobile app embeds these values.  Capture them with
[HTTP Toolkit](https://httptoolkit.com/) or a similar MITM proxy while
performing a login.  See `REVERSE_ENGINEERING.md` for the exact request
shape and confirmed values.

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
| *(other raw props)* | `sensor` | various (diagnostic, disabled by default) |

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
packed = (G << 23) | (B << 15) | (R << 7) + effect_offset
# effect_offset: Constant=4, Pulse=8, Cycle=12, Rhythmic=16
```

---

## Local mock server (development / local control)

See [`mock-server/README.md`](mock-server/README.md) for full instructions.

**Quick start:**

```bash
cd mock-server
npm install
node server.js
# Running at http://0.0.0.0:3000
```

Then in HA, set both **Auth Base URL** and **ADS Base URL** to
`http://<mock-server-ip>:3000` via the integration's **Configure** option.

The mock server accepts any credentials and maintains stateful property
values in memory (writes are reflected in subsequent reads).

For Pi-hole DNS override (so the real Sobro hardware communicates with your
mock server instead of the Ayla cloud), see the mock server README.

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
- **`iot_class: cloud_polling`** even when pointed at a local mock server,
  because HA has no `local_mock` class.  Document caveat, don't fight the field.
- **No `requests` dependency.** All network I/O uses `aiohttp` via HA's own
  session manager — synchronous calls would block the HA event loop.
