"""Time per car: when the parking session ends, or should end when started."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from homeassistant.components.time import TimeEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import normalize_plate
from .const import CONF_CARS, CONF_DESCRIPTION, CONF_LICENSE_PLATE, DEFAULT_END, DOMAIN
from .coordinator import ParkeerserviceConfigEntry, ParkeerserviceCoordinator

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ParkeerserviceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create an end time entity for every car configured in the options.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback to register the entities.
    """
    async_add_entities(
        ParkingEndTime(entry.runtime_data, entry.entry_id, car)
        for car in entry.options.get(CONF_CARS, [])
    )


class ParkingEndTime(CoordinatorEntity[ParkeerserviceCoordinator], TimeEntity, RestoreEntity):
    """End time of the session.

    While a session is active this shows when it ends. Otherwise it is the time
    the next session started with the switch will end (the next time it is that
    time of day).
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ParkeerserviceCoordinator,
        entry_id: str,
        car: Mapping[str, str],
    ) -> None:
        """Initialize the entity.

        Args:
            coordinator: Shared coordinator.
            entry_id: Id of the config entry, used for the unique id.
            car: Car options with description and license plate.
        """
        super().__init__(coordinator)
        self._attr_name = f"{car[CONF_DESCRIPTION]} end time"
        self._plate = normalize_plate(car[CONF_LICENSE_PLATE])
        self._attr_unique_id = f"{entry_id}_{self._plate}_end"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)}, name="Parkeerservice")

    async def async_added_to_hass(self) -> None:
        """Restore the planned end time from before a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            try:
                self.coordinator.planned_end[self._plate] = time.fromisoformat(last.state)
            except ValueError:
                return  # unknown/unavailable, keep the default

    @property
    def native_value(self) -> time:
        """Return the end of the active session, else the planned end."""
        active = [s for s in self.coordinator.data if s.active and s.plate == self._plate]
        if active:
            return dt_util.as_local(max(s.end for s in active)).time().replace(microsecond=0)
        return self.coordinator.planned_end.get(self._plate, DEFAULT_END)

    async def async_set_value(self, value: time) -> None:
        """Plan the end time of the next session.

        Args:
            value: Time of day at which sessions should end.

        Raises:
            HomeAssistantError: If a session is active, as the portal API for
                changing a running session is not supported.
        """
        if any(s.active and s.plate == self._plate for s in self.coordinator.data):
            msg = "A session is running: stop it first, then set the end time and start again"
            raise HomeAssistantError(msg)
        self.coordinator.planned_end[self._plate] = value
        self.async_write_ha_state()
