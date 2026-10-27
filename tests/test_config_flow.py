"""Tests for the config and options flow."""

from unittest.mock import AsyncMock, patch

import pytest
from custom_components.parkeerservice.api import AuthError, ParkeerserviceError
from custom_components.parkeerservice.const import (
    CONF_CARS,
    CONF_DESCRIPTION,
    CONF_LICENSE_PLATE,
    CONF_PERMIT,
    DOMAIN,
)
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import CLIENT, HOST, PERMIT

USER_INPUT = {CONF_HOST: HOST + "/", CONF_EMAIL: "a@b.nl", CONF_PASSWORD: "pw"}


@pytest.mark.usefixtures("client")
async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.parkeerservice.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == HOST
    assert result["options"] == {CONF_CARS: []}


@pytest.mark.parametrize(
    ("exc", "error"),
    [(AuthError("x"), "invalid_auth"), (ParkeerserviceError("x"), "cannot_connect")],
)
async def test_user_flow_errors(hass: HomeAssistant, exc: Exception, error: str) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch(f"{CLIENT}.login", AsyncMock(side_effect=exc)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


@pytest.mark.usefixtures("client")
async def test_user_flow_duplicate(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, data={}, unique_id=f"{HOST}|a@b.nl").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("client")
async def test_options_add_and_remove_car(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["add_car", "remove_car"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_car"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_DESCRIPTION: "Polo", CONF_LICENSE_PLATE: "xy-99-z", CONF_PERMIT: PERMIT.name},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert [c[CONF_LICENSE_PLATE] for c in entry.options[CONF_CARS]] == ["AB123C", "XY99Z"]
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_car"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CARS: ["AB123C"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert [c[CONF_LICENSE_PLATE] for c in entry.options[CONF_CARS]] == ["XY99Z"]


@pytest.mark.usefixtures("client")
async def test_options_menu_without_cars(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_EMAIL: "a@b.nl", CONF_PASSWORD: "pw"},
        options={CONF_CARS: []},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["add_car"]


async def test_reauth_flow(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with patch(f"{CLIENT}.login", AsyncMock(side_effect=AuthError("x"))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "bad"}
        )
    assert result["errors"] == {"base": "invalid_auth"}

    with patch(f"{CLIENT}.login", AsyncMock(side_effect=ParkeerserviceError("x"))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "bad"}
        )
    assert result["errors"] == {"base": "cannot_connect"}

    with (
        patch(f"{CLIENT}.login", AsyncMock()),
        patch("custom_components.parkeerservice.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new"
