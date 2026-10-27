"""The parkeerservice integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AuthError, ParkeerserviceClient, ParkeerserviceError
from .coordinator import ParkeerserviceConfigEntry, ParkeerserviceCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ParkeerserviceConfigEntry) -> bool:
    """Log in and set up the platforms for a config entry.

    Args:
        hass: Home Assistant instance.
        entry: The config entry to set up.

    Returns:
        True once the platforms are forwarded.

    Raises:
        ConfigEntryAuthFailed: If the stored credentials are rejected.
        ConfigEntryNotReady: If the portal cannot be reached.
    """
    client = ParkeerserviceClient(
        async_create_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
    try:
        await client.login()
    except AuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ParkeerserviceError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = ParkeerserviceCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # reload when cars are added or removed in the options
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ParkeerserviceConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ParkeerserviceConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance.
        entry: The config entry to unload.

    Returns:
        Whether the platforms were unloaded.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
