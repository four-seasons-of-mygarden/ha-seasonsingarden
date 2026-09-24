"""Client for the Seasons In Garden sensor Open API.

This module does not depend on Home Assistant so the signing and payload
format can be tested on their own.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import logging
import time
from typing import Any

import aiohttp

from .const import API_METHOD, API_PATH

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


class SeasonsInGardenError(Exception):
    """Base error for the Open API client."""


class CannotConnect(SeasonsInGardenError):
    """The server could not be reached or returned a server error."""


class InvalidAuth(SeasonsInGardenError):
    """The Access Key or signature was rejected."""


class RequestRejected(SeasonsInGardenError):
    """The server rejected the request body."""


@dataclass(frozen=True, slots=True)
class SensorReading:
    """One entry of the request's sensors array."""

    field_nm: str
    category: str
    data: str


def sign(access_key: str, secret_key: str, timestamp: str) -> str:
    """Return the X-Signature header value.

    The signed message is "POST /api/sensor/v1/data", the timestamp and the
    Access Key separated by newlines, with no trailing newline.
    """
    message = f"{API_METHOD} {API_PATH}\n{timestamp}\n{access_key}"
    digest = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def build_payload(
    device_name: str, when: datetime, readings: list[SensorReading]
) -> dict[str, Any]:
    """Return the JSON request body."""
    return {
        "device_name": device_name,
        "date": when.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "sensors": [
            {"field_nm": r.field_nm, "category": r.category, "data": r.data}
            for r in readings
        ],
    }


class SeasonsInGardenClient:
    """Sends signed sensor readings to the Open API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._url = f"https://{host}{API_PATH}"
        self._access_key = access_key
        self._secret_key = secret_key

    async def async_send(self, device_name: str, readings: list[SensorReading]) -> None:
        """Send readings. Raises a SeasonsInGardenError subclass on failure."""
        status, body = await self._async_post(device_name, readings)
        if status in (401, 403):
            raise InvalidAuth(body)
        if 400 <= status < 500:
            raise RequestRejected(f"HTTP {status}: {body}")
        if not 200 <= status < 300:
            raise CannotConnect(f"HTTP {status}: {body}")

    async def async_validate(self, device_name: str) -> None:
        """Check the credentials by sending a request without readings.

        The service has no dedicated validation endpoint yet. Only 401/403
        means the key pair is wrong; a 4xx caused by the empty sensors array
        still proves the signature was accepted.
        """
        status, body = await self._async_post(device_name, [])
        if status in (401, 403):
            raise InvalidAuth(body)
        if status >= 500:
            raise CannotConnect(f"HTTP {status}: {body}")

    async def _async_post(
        self, device_name: str, readings: list[SensorReading]
    ) -> tuple[int, str]:
        now = time.time()
        timestamp = str(int(now * 1000))
        payload = build_payload(device_name, datetime.fromtimestamp(now, UTC), readings)
        headers = {
            "X-API-Key": self._access_key,
            "X-Timestamp": timestamp,
            "X-Signature": sign(self._access_key, self._secret_key, timestamp),
        }
        _LOGGER.debug("Sending %s", payload)
        try:
            async with self._session.post(
                self._url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT
            ) as response:
                body = await response.text()
                _LOGGER.debug("HTTP %s: %s", response.status, body)
                return response.status, body
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(str(err) or type(err).__name__) from err
