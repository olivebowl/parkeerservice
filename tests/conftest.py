"""Shared fixtures."""

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.parkeerservice.api import ParkeerserviceClient, Permit, Session
from custom_components.parkeerservice.const import (
    CONF_CARS,
    CONF_DESCRIPTION,
    CONF_LICENSE_PLATE,
    CONF_PERMIT,
    DOMAIN,
)
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from pytest_homeassistant_custom_component.common import MockConfigEntry

HOST = "https://parkstart-test.parkpermit.eu"
PERMIT = Permit(id=123, product_id=99, name="Bewonersvergunning 1e")
CAR = {
    CONF_DESCRIPTION: "Golf",
    CONF_LICENSE_PLATE: "AB123C",
    CONF_PERMIT: PERMIT.name,
}
CLIENT = "custom_components.parkeerservice.api.ParkeerserviceClient"


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the custom integration."""


@pytest.fixture
def entry() -> MockConfigEntry:
    """Config entry with one car."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_EMAIL: "a@b.nl", CONF_PASSWORD: "pw"},
        options={CONF_CARS: [CAR]},
        unique_id="x",
    )


@pytest.fixture
def client() -> Generator[dict[str, AsyncMock]]:
    """Patch all network calls of the client."""
    sessions = [
        Session(id=1, plate="AB123C", active=False, end=datetime(2020, 1, 1, tzinfo=UTC)),
    ]

    async def login(self: ParkeerserviceClient) -> None:
        self.customer_id = 567
        self.permits = [PERMIT]

    mocks: dict[str, Any] = {
        "get_sessions": AsyncMock(return_value=sessions),
        "start": AsyncMock(),
        "stop": AsyncMock(),
    }
    with (
        patch(f"{CLIENT}.login", login),
        patch(f"{CLIENT}.get_sessions", mocks["get_sessions"]),
        patch(f"{CLIENT}.start", mocks["start"]),
        patch(f"{CLIENT}.stop", mocks["stop"]),
    ):
        yield mocks
