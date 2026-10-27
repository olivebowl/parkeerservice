"""UI setup: credentials in the config flow, cars in the options flow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import AuthError, ParkeerserviceClient, ParkeerserviceError, normalize_plate
from .const import CONF_CARS, CONF_DESCRIPTION, CONF_LICENSE_PLATE, CONF_PERMIT, DOMAIN

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .coordinator import ParkeerserviceConfigEntry

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ParkeerserviceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the portal url and credentials, and check that they work."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the first step where the user enters the portal and credentials.

        Args:
            user_input: Submitted form data, or None when the form is first shown.

        Returns:
            The form to show, or the created entry.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip().rstrip("/")
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}|{user_input[CONF_EMAIL]}".lower()
            )
            self._abort_if_unique_id_configured()
            client = ParkeerserviceClient(
                async_create_clientsession(self.hass),
                user_input[CONF_HOST],
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.login()
            except AuthError:
                errors["base"] = "invalid_auth"
            except ParkeerserviceError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL], data=user_input, options={CONF_CARS: []}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            description_placeholders={"example": "https://parkstart-LOCATION.parkpermit.eu"},
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],  # noqa: ARG002
    ) -> ConfigFlowResult:
        """Start re-authentication after the portal rejected the stored password.

        Args:
            entry_data: Data of the entry that needs new credentials.

        Returns:
            The password form.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password.

        Args:
            user_input: Submitted form data, or None when the form is first shown.

        Returns:
            The form to show, or the abort once the entry is updated.
        """
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            client = ParkeerserviceClient(
                async_create_clientsession(self.hass),
                entry.data[CONF_HOST],
                entry.data[CONF_EMAIL],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.login()
            except AuthError:
                errors["base"] = "invalid_auth"
            except ParkeerserviceError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ParkeerserviceConfigEntry) -> OptionsFlow:  # noqa: ARG004
        """Return the options flow used to manage cars.

        Args:
            config_entry: The entry to manage.

        Returns:
            The options flow.
        """
        return ParkeerserviceOptionsFlow()


class ParkeerserviceOptionsFlow(OptionsFlow):
    """Add and remove cars; the permit is picked from the account's permits."""

    config_entry: ParkeerserviceConfigEntry

    @property
    def _cars(self) -> list[dict[str, str]]:
        return list(self.config_entry.options.get(CONF_CARS, []))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:  # noqa: ARG002
        """Show the menu.

        Args:
            user_input: Unused, the menu has no form.

        Returns:
            The menu result.
        """
        menu = ["add_car", "remove_car"] if self._cars else ["add_car"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_car(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a car.

        Args:
            user_input: Submitted form data, or None when the form is first shown.

        Returns:
            The form to show, or the saved options.
        """
        if user_input is not None:
            user_input[CONF_LICENSE_PLATE] = normalize_plate(user_input[CONF_LICENSE_PLATE])
            return self.async_create_entry(data={CONF_CARS: [*self._cars, user_input]})

        permits = self.config_entry.runtime_data.client.permits
        schema = vol.Schema(
            {
                vol.Required(CONF_DESCRIPTION): str,
                vol.Required(CONF_LICENSE_PLATE): str,
                vol.Required(CONF_PERMIT): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=p.name, label=p.name) for p in permits],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="add_car", data_schema=schema)

    async def async_step_remove_car(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove cars.

        Args:
            user_input: Submitted form data, or None when the form is first shown.

        Returns:
            The form to show, or the saved options.
        """
        cars = self._cars
        if user_input is not None:
            remove = set(user_input[CONF_CARS])
            kept = [c for c in cars if c[CONF_LICENSE_PLATE] not in remove]
            return self.async_create_entry(data={CONF_CARS: kept})

        schema = vol.Schema(
            {
                vol.Required(CONF_CARS): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=c[CONF_LICENSE_PLATE],
                                label=f"{c[CONF_DESCRIPTION]} ({c[CONF_LICENSE_PLATE]})",
                            )
                            for c in cars
                        ],
                        multiple=True,
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_car", data_schema=schema)
