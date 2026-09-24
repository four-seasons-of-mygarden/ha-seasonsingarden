"""Tests for the Open API client."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.seasonsingarden.api import (
    CannotConnect,
    InvalidAuth,
    RequestRejected,
    SeasonsInGardenClient,
    SensorReading,
    build_payload,
    sign,
)

from .conftest import ACCESS_KEY, SECRET_KEY

URL = "https://collector.example/api/sensor/v1/data"


@pytest.fixture
def client(hass: HomeAssistant) -> SeasonsInGardenClient:
    """Return a client using Home Assistant's mocked session."""
    return SeasonsInGardenClient(
        async_get_clientsession(hass), "collector.example", ACCESS_KEY, SECRET_KEY
    )


def test_sign_matches_reference() -> None:
    """The signature matches one computed independently with OpenSSL."""
    # printf 'POST /api/sensor/v1/data\n1790000000000\ntest-access-key' \
    #   | openssl dgst -sha256 -hmac 'test-secret-key' -binary | base64
    assert (
        sign(ACCESS_KEY, SECRET_KEY, "1790000000000")
        == "9llhl67V5GtM+JRvVkJrjeII3bNHHimhDN+KJLFLGWQ="
    )


def test_build_payload_uses_utc() -> None:
    """The date is formatted in UTC even for aware local times."""
    when = datetime.fromisoformat("2026-09-22T21:00:00+09:00")
    payload = build_payload("베란다 화분", when, [SensorReading("temp", "01", "24.5")])
    assert payload == {
        "device_name": "베란다 화분",
        "date": "2026-09-22 12:00:00",
        "sensors": [{"field_nm": "temp", "category": "01", "data": "24.5"}],
    }


async def test_send_signs_request(
    aioclient_mock: AiohttpClientMocker, client: SeasonsInGardenClient
) -> None:
    """Sending posts the payload with the authentication headers."""
    aioclient_mock.post(URL, text="데이터 수신 성공")
    with patch(
        "custom_components.seasonsingarden.api.time.time", return_value=1790000000.0
    ):
        await client.async_send("pot", [SensorReading("temp", "01", "24.5")])

    _method, _url, body, headers = aioclient_mock.mock_calls[0]
    assert headers["X-API-Key"] == ACCESS_KEY
    assert headers["X-Timestamp"] == "1790000000000"
    assert headers["X-Signature"] == "9llhl67V5GtM+JRvVkJrjeII3bNHHimhDN+KJLFLGWQ="
    assert body == {
        "device_name": "pot",
        "date": datetime.fromtimestamp(1790000000, UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "sensors": [{"field_nm": "temp", "category": "01", "data": "24.5"}],
    }


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, InvalidAuth),
        (403, InvalidAuth),
        (400, RequestRejected),
        (500, CannotConnect),
    ],
)
async def test_send_errors(
    aioclient_mock: AiohttpClientMocker,
    client: SeasonsInGardenClient,
    status: int,
    error: type[Exception],
) -> None:
    """HTTP errors map to client exceptions."""
    aioclient_mock.post(URL, status=status, text="Invalid Signature")
    with pytest.raises(error):
        await client.async_send("pot", [SensorReading("temp", "01", "1")])


@pytest.mark.parametrize(
    ("status", "error"),
    [(200, None), (400, None), (401, InvalidAuth), (503, CannotConnect)],
)
async def test_validate(
    aioclient_mock: AiohttpClientMocker,
    client: SeasonsInGardenClient,
    status: int,
    error: type[Exception] | None,
) -> None:
    """Only authentication and server errors fail validation."""
    aioclient_mock.post(URL, status=status)
    if error is None:
        await client.async_validate("pot")
    else:
        with pytest.raises(error):
            await client.async_validate("pot")
    assert aioclient_mock.mock_calls[0][2]["sensors"] == []
