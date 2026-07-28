# Sobro mock server

Standalone Node.js/Express server that impersonates the Ayla Networks cloud
API used by Sobro Smart Furniture devices.

> **This is NOT part of the HACS integration.**
> It lives in `mock-server/` and is installed and run separately.
> HACS installs only `custom_components/sobro/` — this directory is ignored
> by that flow entirely.

---

## How the mock server relates to the integration

The integration's `api.py` accepts configurable `auth_url` and `ads_url`
fields.  In normal use both point at the real Ayla cloud endpoints.  To use
the mock server instead, you change **only those two URL fields** in the
integration's options — no code changes required in either piece.

```
Real cloud mode:
  auth_url = https://user-field.aylanetworks.com
  ads_url  = https://ads-field.aylanetworks.com

Mock server mode (direct URL override):
  auth_url = http://192.168.1.100:3000
  ads_url  = http://192.168.1.100:3000
```

---

## Quick start — direct URL override (simplest)

```bash
cd mock-server
npm install
node server.js
# Server is now at http://0.0.0.0:3000
```

Then in Home Assistant:

1. Go to **Settings → Devices & Services → Sobro → Configure**.
2. Set **Auth Base URL** and **ADS Base URL** both to
   `http://<mock-server-ip>:3000`.
3. Save — the integration immediately re-authenticates against the mock.

The mock accepts **any** email/password and returns fake tokens.

---

## Docker / Docker Compose

```bash
cd mock-server
docker compose up --build
```

---

## Pi-hole DNS override (production-style local control)

This approach lets the real Sobro table firmware communicate with your mock
server instead of the Ayla cloud, without modifying the device or the HA
integration URLs.

### Prerequisites

- Pi-hole running on your local network
- A machine reachable at a static LAN IP (the mock server host)
- **HTTPS** required — the Sobro firmware likely validates TLS (see
  feasibility note below)

### Steps

1. **Run the mock server on port 443** (or use a reverse proxy like Caddy):

   ```bash
   # Using Caddy with a self-signed cert for testing:
   caddy reverse-proxy --from :443 --to localhost:3000
   ```

2. **Add Pi-hole local DNS overrides:**

   In Pi-hole admin → Local DNS → DNS Records, add:

   | Domain | IP |
   |--------|----|
   | `user-field.aylanetworks.com` | `<mock-server-LAN-IP>` |
   | `ads-field.aylanetworks.com`  | `<mock-server-LAN-IP>` |

3. **Test TLS handshake feasibility first (do this before investing further):**

   - The table may pin certificates or validate against a specific CA.
   - Run `openssl s_server -cert selfsigned.crt -key selfsigned.key -port 443`
     on the mock host, then trigger a login from the table.
   - **If the TLS handshake completes** → the firmware accepts self-signed
     certs → full mock server is viable.
   - **If the TLS handshake fails** → the firmware pins certs or requires a
     trusted CA → local control at the firmware level may require more work.

### HTTPS self-signed cert (quick test)

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem \
  -days 365 -nodes -subj "/CN=user-field.aylanetworks.com"

# Then run with HTTPS support:
PORT=443 node -e "
  const https = require('https');
  const fs = require('fs');
  const app = require('./server');
  https.createServer(
    { key: fs.readFileSync('key.pem'), cert: fs.readFileSync('cert.pem') },
    app
  ).listen(443);
"
```

> The `server.js` exports `app` for this purpose — modify the final
> `app.listen(PORT, ...)` call to instead export `module.exports = app`
> if you need this pattern.

---

## Implemented endpoints

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/users/sign_in.json` | Accepts any credentials; returns fake tokens |
| `POST` | `/users/refresh_token.json` | Returns refreshed fake tokens |
| `GET`  | `/apiv1/devices.json` | Returns two mock nightstands |
| `GET`  | `/apiv1/dsns/:dsn/properties.json` | Returns all properties for a DSN |
| `POST` | `/apiv1/properties/:id/datapoints.json` | **Returns 201** (not 200); persists value in memory |

### Mock devices

| DSN | Name |
|-----|------|
| `AC000W000000001` | Sobro Nightstand Left |
| `AC000W000000002` | Sobro Nightstand Right |

Property state is stored in memory — writes are reflected in subsequent
reads within the same server process.  State resets when the server restarts.

---

## Adding fixture data from real captures

Drop captured `properties.json` responses from real hardware into
`fixtures/` and load them in `server.js` instead of the `defaultProps()`
function to replay real property values exactly.
