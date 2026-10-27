"""Shared data coordinator: one login and one sessions request for all cars."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, ParkeerserviceClient, ParkeerserviceError, Session
from .const import DOMAIN, UPDATE_INTERVAL

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

type ParkeerserviceConfigEntry = ConfigEntry[ParkeerserviceCoordinator]


class ParkeerserviceCoordinator(DataUpdateCoordinator[list[Session]]):
    """Polls the sessions of the account and relays start/stop calls."""

    config_entry: ParkeerserviceConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ParkeerserviceConfigEntry,
        client: ParkeerserviceClient,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            config_entry: Entry this coordinator belongs to.
            client: Logged in client used for all requests.
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> list[Session]:
        """Fetch the sessions, logging in again once if the cookie expired."""
        try:
            try:
                return await self.client.get_sessions()
            except AuthError:
                await self.client.login()
                return await self.client.get_sessions()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ParkeerserviceError as err:
            raise UpdateFailed(str(err)) from err

    async def async_call[**P](
        self,
        func: Callable[P, Awaitable[None]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        """Run a start/stop call and refresh, logging in again once if expired.

        Args:
            func: Client method to call.
            *args: Positional arguments for `func`.
            **kwargs: Keyword arguments for `func`.

        Raises:
            HomeAssistantError: If the call fails.
        """
        try:
            try:
                await func(*args, **kwargs)
            except AuthError:
                await self.client.login()
                await func(*args, **kwargs)
        except ParkeerserviceError as err:
            raise HomeAssistantError(str(err)) from err
        await self.async_refresh()
