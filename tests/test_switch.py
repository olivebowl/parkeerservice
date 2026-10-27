"""Tests for setup, the coordinator and the switch."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.parkeerservice.api import AuthError, ParkeerserviceError, Session
from custom_components.parkeerservice.const import UPDATE_INTERVAL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from .conftest import CLIENT

ENTITY = "switch.parkeerservice_golf"


def active_session() -> Session:
    return Session(id=9, plate="AB123C", active=True, end=datetime(2099, 1, 1, tzinfo=UTC))


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def poll(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, datetime.now(UTC) + UPDATE_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()


def state(hass: HomeAssistant) -> str:
    found = hass.states.get(ENTITY)
    assert found is not None
    return found.state


async def test_state_off_then_on(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    await setup(hass, entry)
    assert state(hass) == STATE_OFF
    client["get_sessions"].return_value = [active_session()]
    await poll(hass)
    assert state(hass) == STATE_ON


async def test_turn_on_starts_session(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    await setup(hass, entry)
    client["get_sessions"].reset_mock()
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: ENTITY}, blocking=True)
    client["start"].assert_awaited_once()
    args = client["start"].await_args
    assert args is not None
    assert args.args[:2] == ("AB123C", "Bewonersvergunning 1e")
    # exactly one refresh after the action, no extra polling
    assert client["get_sessions"].await_count == 1


async def test_turn_on_when_already_on_does_nothing(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    client["get_sessions"].return_value = [active_session()]
    await setup(hass, entry)
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: ENTITY}, blocking=True)
    client["start"].assert_not_awaited()


async def test_turn_off_stops_session(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    client["get_sessions"].return_value = [active_session()]
    await setup(hass, entry)
    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: ENTITY}, blocking=True)
    client["stop"].assert_awaited_once_with(9)


async def test_action_error_is_raised(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    await setup(hass, entry)
    client["start"].side_effect = ParkeerserviceError("nope")
    with pytest.raises(HomeAssistantError, match="nope"):
        await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: ENTITY}, blocking=True)


async def test_action_relogs_in_once_on_expired_session(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    await setup(hass, entry)
    client["start"].side_effect = [AuthError("expired"), None]
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: ENTITY}, blocking=True)
    assert client["start"].await_count == 2


async def test_poll_relogs_in_on_expired_session(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    await setup(hass, entry)
    client["get_sessions"].side_effect = [AuthError("expired"), [active_session()]]
    await poll(hass)
    assert state(hass) == STATE_ON


async def test_poll_auth_failure_triggers_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    await setup(hass, entry)
    client["get_sessions"].side_effect = AuthError("expired")
    await poll(hass)
    assert list(entry.async_get_active_flows(hass, {"reauth"}))


async def test_poll_error_marks_unavailable(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    await setup(hass, entry)
    client["get_sessions"].side_effect = ParkeerserviceError("down")
    await poll(hass)
    assert state(hass) == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (AuthError("x"), ConfigEntryState.SETUP_ERROR),
        (ParkeerserviceError("x"), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_setup_login_failures(
    hass: HomeAssistant, entry: MockConfigEntry, exc: Exception, expected: ConfigEntryState
) -> None:
    with patch(f"{CLIENT}.login", AsyncMock(side_effect=exc)):
        await setup(hass, entry)
    assert entry.state is expected


@pytest.mark.usefixtures("client")
async def test_unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await setup(hass, entry)
    await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
