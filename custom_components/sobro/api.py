"""Ayla Networks REST client for the Sobro integration.

Handles authentication, token refresh, device discovery, and property
read/write.  All network I/O is async (aiohttp), which is a hard requirement
for Home Assistant integrations — never use the synchronous ``requests``
library inside an integration, as it blocks the HA event loop.

Key Ayla quirks captured here so they are not re-discovered:
- Sign-in is POST to ``user-field`` (auth) host.
- Device/property calls are POST/GET to ``ads-field`` (ADS) host.
- The Authorization header is ``auth_token <token>`` for most endpoints;
  some newer endpoints use ``****** — this client uses
  ``auth_token`` everywhere and notes the alternative where relevant.
- A successful property write returns **201 Created**, not 200.
- Token refresh uses a separate ``refresh_token.json`` endpoint; the client
  retries automatically on 401 responses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class SobroAuthError(Exception):
    """Raised on authentication failures (bad credentials, expired refresh token)."""


class SobroApiError(Exception):
    """Raised on non-auth API failures."""


class PropertyData:
    """Lightweight container for a single Ayla property snapshot."""

    __slots__ = ("property_id", "value", "name")

    def __init__(self, property_id: int, value: Any, name: str) -> None:
        self.property_id = property_id
        self.value = value
        self.name = name

    def __repr__(self) -> str:
        return f"PropertyData(name={self.name!r}, value={self.value!r}, id={self.property_id})"


class SobroApiClient:
    """Async Ayla Networks client for Sobro devices.

    One client instance is shared across all per-DSN coordinators belonging
    to the same config entry.  Tokens are kept in memory; on HA restart the
    client re-authenticates from the stored credentials.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        app_id: str,
        app_secret: str,
        auth_url: str,
        ads_url: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._app_id = app_id
        self._app_secret = app_secret
        self._auth_url = auth_url.rstrip("/")
        self._ads_url = ads_url.rstrip("/")

        self._access_token: str | None = None
        self._refresh_token: str | None = None

    # ── Public auth helpers ────────────────────────────────────────────────────

    async def async_sign_in(self) -> None:
        """Authenticate with Ayla and store access + refresh tokens."""
        payload = {
            "user": {
                "email": self._email,
                "password": self._password,
                "application": {
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                },
            }
        }
        data = await self._post_auth("/users/sign_in.json", payload, authenticated=False)
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        _LOGGER.debug("Sobro: signed in successfully")

    async def async_refresh_token(self) -> None:
        """Use the refresh token to obtain a new access token."""
        if not self._refresh_token:
            raise SobroAuthError("No refresh token available; re-authentication required")
        payload = {"user": {"refresh_token": self._refresh_token}}
        try:
            data = await self._post_auth("/users/refresh_token.json", payload, authenticated=False)
        except SobroAuthError:
            # Refresh token is also expired — force full re-auth.
            await self.async_sign_in()
            return
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        _LOGGER.debug("Sobro: token refreshed")

    # ── Device discovery ───────────────────────────────────────────────────────

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return a list of device dicts, each containing at minimum 'dsn'."""
        raw = await self._get_ads("/apiv1/devices.json")
        # Normalise: the API returns either a top-level list or {"devices": [...]}
        if isinstance(raw, list):
            entries = raw
        else:
            entries = raw.get("devices", [])
        return [entry["device"] for entry in entries if "device" in entry]

    # ── Property I/O ───────────────────────────────────────────────────────────

    async def async_get_properties(self, dsn: str) -> dict[str, PropertyData]:
        """Fetch all properties for *dsn* and return them keyed by property name."""
        raw: list[dict[str, Any]] = await self._get_ads(f"/apiv1/dsns/{dsn}/properties.json")
        result: dict[str, PropertyData] = {}
        for entry in raw:
            prop = entry.get("property", {})
            name = prop.get("name")
            key = prop.get("key")
            value = prop.get("value")
            if name is not None and key is not None:
                result[name] = PropertyData(property_id=int(key), value=value, name=name)
        return result

    async def async_set_property(self, property_id: int, value: Any) -> None:
        """Write a new value to a property by its numeric ID.

        Ayla returns **201 Created** on success, not 200 — this is intentional
        and has caused integration bugs before; do not treat 201 as an error.
        """
        payload = {"datapoint": {"value": value}}
        await self._post_ads(
            f"/apiv1/properties/{property_id}/datapoints.json",
            payload,
            expected_status=201,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            raise SobroAuthError("Not authenticated; call async_sign_in() first")
        # Most Ayla endpoints use "auth_token"; some newer ones want "Bearer".
        return {"Authorization": f"auth_token {self._access_token}"}

    async def _post_auth(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        url = f"{self._auth_url}{path}"
        headers = self._auth_headers() if authenticated else {}
        return await self._request("POST", url, json=payload, headers=headers, expected_status=200)

    async def _get_ads(self, path: str) -> Any:
        url = f"{self._ads_url}{path}"
        return await self._request("GET", url, headers=self._auth_headers(), expected_status=200)

    async def _post_ads(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        expected_status: int = 200,
    ) -> Any:
        url = f"{self._ads_url}{path}"
        return await self._request(
            "POST", url, json=payload, headers=self._auth_headers(), expected_status=expected_status
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected_status: int,
        _retry: bool = True,
    ) -> Any:
        try:
            async with self._session.request(
                method, url, json=json, headers=headers, timeout=_REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 401 and _retry:
                    _LOGGER.debug("Sobro: got 401, attempting token refresh")
                    await self.async_refresh_token()
                    # Rebuild headers with the new token and retry once.
                    new_headers = self._auth_headers() if headers else {}
                    return await self._request(
                        method, url, json=json, headers=new_headers,
                        expected_status=expected_status, _retry=False,
                    )
                if resp.status in (401, 403):
                    raise SobroAuthError(f"Authentication error {resp.status} from {url}")
                if resp.status != expected_status:
                    body = await resp.text()
                    raise SobroApiError(
                        f"Unexpected HTTP {resp.status} (expected {expected_status}) "
                        f"from {url}: {body[:200]}"
                    )
                # 201 responses may have no body
                if resp.content_length == 0 or resp.status == 201:
                    return {}
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise SobroApiError(f"Connection error to {url}: {exc}") from exc
