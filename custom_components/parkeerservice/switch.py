"""Switch per car: on means a parking session is active, toggling starts/stops it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Session, normalize_plate
from .const import CONF_CARS, CONF_DESCRIPTION, CONF_LICENSE_PLATE, CONF_PERMIT, DOMAIN
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
    """Create a switch for every car configured in the options.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback to register the entities.
    """
    async_add_entities(
        ParkingSwitch(entry.runtime_data, entry.entry_id, car)
        for car in entry.options.get(CONF_CARS, [])
    )


class ParkingSwitch(CoordinatorEntity[ParkeerserviceCoordinator], SwitchEntity):
    """A car that can be parked."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ParkeerserviceCoordinator,
        entry_id: str,
        car: Mapping[str, str],
    ) -> None:
        """Initialize the switch.

        Args:
            coordinator: Shared coordinator.
            entry_id: Id of the config entry, used for the unique id.
            car: Car options with description, license plate and permit.
        """
        super().__init__(coordinator)
        self._attr_name = car[CONF_DESCRIPTION]
        self._plate = normalize_plate(car[CONF_LICENSE_PLATE])
        self._permit = car[CONF_PERMIT]
        self._attr_unique_id = f"{entry_id}_{self._plate}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)}, name="Parkeerservice")

    def _active_sessions(self) -> list[Session]:
        return [s for s in self.coordinator.data if s.active and s.plate == self._plate]

    @property
    def is_on(self) -> bool:
        """Return whether a session is active for this car."""
        return bool(self._active_sessions())

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ANN401, ARG002
        """Start a session lasting until the planned end time."""
        if self.is_on:
            return
        end = self.coordinator.next_end(self._plate)
        await self.coordinator.async_call(
            self.coordinator.client.start, self._plate, self._permit, end
        )

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ANN401, ARG002
        """Stop all active sessions of this car."""
        for session in self._active_sessions():
            await self.coordinator.async_call(self.coordinator.client.stop, session.id)
