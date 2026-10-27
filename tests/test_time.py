"""Tests for the end time entity and the planned end of sessions."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from custom_components.parkeerservice.api import Session
from custom_components.parkeerservice.const import DEFAULT_END
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache

from .test_switch import setup

ENTITY = "time.parkeerservice_golf_end_time"
SWITCH = "switch.parkeerservice_golf"


def value(hass: HomeAssistant) -> str:
    found = hass.states.get(ENTITY)
    assert found is not None
    return found.state


async def set_time(hass: HomeAssistant, at: str) -> None:
    await hass.services.async_call(
        "time", "set_value", {ATTR_ENTITY_ID: ENTITY, "time": at}, blocking=True
    )


@pytest.mark.usefixtures("client")
async def test_default_is_end_of_day(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config.async_set_time_zone("UTC")
    await setup(hass, entry)
    assert value(hass) == DEFAULT_END.isoformat()


async def test_planned_end_is_used_when_starting(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: dict[str, AsyncMock],
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-01-01 12:00:00")
    await hass.config.async_set_time_zone("UTC")
    await setup(hass, entry)
    await set_time(hass, "17:30:00")
    assert value(hass) == "17:30:00"
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    args = client["start"].await_args
    assert args is not None
    end = args.args[2]
    assert end == datetime(2026, 1, 1, 17, 30, tzinfo=UTC)


async def test_planned_end_in_the_past_means_tomorrow(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: dict[str, AsyncMock],
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-01-01 12:00:00")
    await hass.config.async_set_time_zone("UTC")
    await setup(hass, entry)
    await set_time(hass, "09:00:00")
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    args = client["start"].await_args
    assert args is not None
    assert args.args[2] == datetime(2026, 1, 2, 9, tzinfo=UTC)


async def test_shows_end_of_active_session_and_refuses_changes(
    hass: HomeAssistant, entry: MockConfigEntry, client: dict[str, AsyncMock]
) -> None:
    client["get_sessions"].return_value = [
        Session(id=9, plate="AB123C", active=True, end=datetime(2099, 1, 1, 8, 15, tzinfo=UTC))
    ]
    await hass.config.async_set_time_zone("UTC")
    await setup(hass, entry)
    assert value(hass) == "08:15:00"
    with pytest.raises(HomeAssistantError, match="stop it first"):
        await set_time(hass, "10:00:00")


@pytest.mark.usefixtures("client")
async def test_restores_planned_end(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    mock_restore_cache(hass, [State(ENTITY, "16:45:00")])
    await hass.config.async_set_time_zone("UTC")
    await setup(hass, entry)
    assert value(hass) == "16:45:00"


@pytest.mark.usefixtures("client")
async def test_ignores_unrestorable_state(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    mock_restore_cache(hass, [State(ENTITY, STATE_UNKNOWN)])
    await hass.config.async_set_time_zone("UTC")
    await setup(hass, entry)
    assert value(hass) == DEFAULT_END.isoformat()
