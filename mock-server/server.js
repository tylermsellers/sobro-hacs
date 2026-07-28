/**
 * Sobro mock server — impersonates the Ayla Networks cloud API.
 *
 * This is a STANDALONE development tool, NOT part of the HACS integration.
 * It lives in mock-server/ and is run independently (Node.js or Docker).
 * The custom_components/sobro/ integration package does not reference or
 * depend on this file in any way.
 *
 * Usage:
 *   npm install && node server.js
 *   # or: docker compose up
 *
 * Then set the integration's "Auth Base URL" and "ADS Base URL" both to
 *   http://<this-machine-ip>:3000
 *
 * For production-style Pi-hole DNS override (HTTPS), see README.md.
 *
 * Implements:
 *   POST /users/sign_in.json
 *   POST /users/refresh_token.json
 *   GET  /apiv1/devices.json
 *   GET  /apiv1/dsns/:dsn/properties.json
 *   POST /apiv1/properties/:propertyId/datapoints.json  -> 201
 */

"use strict";

const express = require("express");
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;

// Fake tokens — accept any credentials and return these.
const FAKE_ACCESS_TOKEN  = "mock_access_token_sobro";
const FAKE_REFRESH_TOKEN = "mock_refresh_token_sobro";

// ── Mock device registry ───────────────────────────────────────────────────────
const devices = {
  "AC000W000000001": {
    dsn: "AC000W000000001",
    product_name: "Sobro Nightstand Left",
    model: "sobro_ns",
    sw_version: "1.2.3",
  },
  "AC000W000000002": {
    dsn: "AC000W000000002",
    product_name: "Sobro Nightstand Right",
    model: "sobro_ns",
    sw_version: "1.2.3",
  },
};

// Property state per DSN.
// flight_status format: "autoMode:brightness:duration:colorTempK"
// mode_status: packed (G<<23)|(B<<15)|(R<<7) + effect offset
function defaultProps(idBase) {
  return {
    F_key:          { key: idBase+1,  name: "F_key",          base_type: "boolean", value: 0 },
    B_key:          { key: idBase+2,  name: "B_key",          base_type: "boolean", value: 0 },
    Cooling_switch: { key: idBase+3,  name: "Cooling_switch", base_type: "boolean", value: 0 },
    Drawer_lock:    { key: idBase+4,  name: "Drawer_lock",    base_type: "boolean", value: 0 },
    ble_switch:     { key: idBase+5,  name: "ble_switch",     base_type: "boolean", value: 0 },
    brightness:     { key: idBase+6,  name: "brightness",     base_type: "integer", value: 50 },
    flight_status:  { key: idBase+7,  name: "flight_status",  base_type: "string",  value: "0:50:60:3000" },
    mode_status:    { key: idBase+8,  name: "mode_status",    base_type: "integer", value: 4 },
    version:        { key: idBase+9,  name: "version",        base_type: "string",  value: "1.2.3" },
    adjust_br:      { key: idBase+10, name: "adjust_br",      base_type: "integer", value: 0 },
    Attribute:      { key: idBase+11, name: "Attribute",      base_type: "string",  value: "" },
    custom_list:    { key: idBase+12, name: "custom_list",    base_type: "string",  value: "" },
    disconnect_ble: { key: idBase+13, name: "disconnect_ble", base_type: "boolean", value: 0 },
    get_snapshot:   { key: idBase+14, name: "get_snapshot",   base_type: "string",  value: "" },
    key:            { key: idBase+15, name: "key",            base_type: "string",  value: "" },
    main_list:      { key: idBase+16, name: "main_list",      base_type: "string",  value: "" },
  };
}

const propertyState = {
  "AC000W000000001": defaultProps(1000),
  "AC000W000000002": defaultProps(2000),
};

// Reverse map: property ID -> {dsn, propName}
const propIdIndex = {};
for (const [dsn, props] of Object.entries(propertyState)) {
  for (const [name, prop] of Object.entries(props)) {
    propIdIndex[prop.key] = { dsn, name };
  }
}

// ── Auth middleware ────────────────────────────────────────────────────────────
function requireAuth(req, res, next) {
  const auth = req.headers["authorization"] || "";
  const valid = [
    "auth_token " + FAKE_ACCESS_TOKEN,
    "Bearer "     + FAKE_ACCESS_TOKEN,
  ];
  if (valid.includes(auth)) return next();
  console.warn("[401]", req.method, req.path, "bad token:", auth);
  res.status(401).json({ error: "Unauthorized" });
}

// ── Routes ─────────────────────────────────────────────────────────────────────

app.post("/users/sign_in.json", (req, res) => {
  const user = req.body && req.body.user ? req.body.user : {};
  console.log("[sign_in] email=" + user.email);
  res.json({
    access_token:  FAKE_ACCESS_TOKEN,
    refresh_token: FAKE_REFRESH_TOKEN,
    expires_in:    86400,
    role:          "EndUser",
  });
});

app.post("/users/refresh_token.json", (req, res) => {
  console.log("[refresh_token]");
  res.json({
    access_token:  FAKE_ACCESS_TOKEN,
    refresh_token: FAKE_REFRESH_TOKEN,
    expires_in:    86400,
  });
});

app.get("/apiv1/devices.json", requireAuth, (req, res) => {
  res.json(Object.values(devices).map(function(d) { return { device: d }; }));
});

app.get("/apiv1/dsns/:dsn/properties.json", requireAuth, (req, res) => {
  var dsn = req.params.dsn;
  var props = propertyState[dsn];
  if (!props) return res.status(404).json({ error: "Unknown DSN: " + dsn });
  res.json(Object.values(props).map(function(p) { return { property: Object.assign({}, p) }; }));
});

// Writes return 201 — this is intentional Ayla behaviour, not a bug.
app.post("/apiv1/properties/:propertyId/datapoints.json", requireAuth, (req, res) => {
  var propertyId = parseInt(req.params.propertyId, 10);
  var value      = req.body && req.body.datapoint ? req.body.datapoint.value : undefined;
  var ref        = propIdIndex[propertyId];

  if (!ref) return res.status(404).json({ error: "Unknown property ID: " + propertyId });

  propertyState[ref.dsn][ref.name].value = value;
  console.log("[write] DSN=" + ref.dsn + " prop=" + ref.name + " value=" + JSON.stringify(value));

  res.status(201).json({
    datapoint: { id: Date.now(), updated_at: new Date().toISOString(), value: value },
  });
});

// ── Start ──────────────────────────────────────────────────────────────────────
app.listen(PORT, function() {
  console.log("Sobro mock server running on http://0.0.0.0:" + PORT);
  console.log("Mock DSNs:", Object.keys(devices).join(", "));
  console.log("Set auth_url and ads_url in the HA integration to http://<host>:" + PORT);
});
