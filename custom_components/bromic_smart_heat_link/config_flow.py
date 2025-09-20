"""Config flow for Bromic Smart Heat Link integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_CONTROLLER_TYPE,
    CONF_CONTROLLERS,
    CONF_ID_LOCATION,
    CONF_LEARNED_BUTTONS,
    CONF_SERIAL_PORT,
    CONTROLLER_TYPE_DIMMER,
    CONTROLLER_TYPE_ONOFF,
    DIMMER_BUTTONS,
    DOMAIN,
    MAX_ID_LOCATION,
    MIN_ID_LOCATION,
    ONOFF_BUTTONS,
)
from .exceptions import BromicLearningError
from .hub import BromicHub

if TYPE_CHECKING:
    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL_PORT): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bromic Smart Heat Link."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._hub: BromicHub | None = None
        self._discovered_ports: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await self._test_connection(user_input[CONF_SERIAL_PORT])
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Bromic Smart Heat Link ({user_input[CONF_SERIAL_PORT]})",
                    data=user_input,
                    options={CONF_CONTROLLERS: {}},
                )

        # Discover available ports
        if not self._discovered_ports:
            self._discovered_ports = await BromicHub.discover_ports()

        # Create schema with discovered ports
        if self._discovered_ports:
            port_options = {
                port["device"]: f"{port['device']} - {port['description']}"
                for port in self._discovered_ports
            }
            schema = vol.Schema(
                {
                    vol.Required(CONF_SERIAL_PORT): vol.In(port_options),
                }
            )
        else:
            schema = STEP_USER_DATA_SCHEMA

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"port_count": str(len(self._discovered_ports))},
        )

    async def _test_connection(self, port: str) -> None:
        """Test connection to the device."""
        hub = BromicHub(self.hass, port)
        try:
            await hub.async_connect()
            await hub.async_test_connection()
        except Exception as err:
            _LOGGER.exception("Connection test failed")
            raise CannotConnectError from err
        finally:
            await hub.async_disconnect()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Bromic Smart Heat Link."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._hub: BromicHub | None = None
        self._learning_id: int | None = None
        self._learning_type: str | None = None
        self._learning_buttons: dict[int, bool] = {}
        self._current_button: int = 1

    async def async_step_init(
        self, _user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "change_serial_port",
                "add_controller",
                "manage_controllers",
                "advanced_settings",
            ],
        )

    async def async_step_add_controller(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new controller."""
        errors: dict[str, str] = {}

        if user_input is not None:
            id_location = user_input[CONF_ID_LOCATION]
            controller_type = user_input[CONF_CONTROLLER_TYPE]

            # Check if ID is already used
            controllers = self.config_entry.options.get(CONF_CONTROLLERS, {})
            if str(id_location) in controllers:
                errors["base"] = "id_already_used"
            else:
                # Start learning process
                self._learning_id = id_location
                self._learning_type = controller_type
                self._learning_buttons = {}
                self._current_button = 1

                return await self.async_step_learn_buttons()

        # Get used IDs
        controllers = self.config_entry.options.get(CONF_CONTROLLERS, {})
        used_ids = [int(id_str) for id_str in controllers]
        available_ids = [
            i for i in range(MIN_ID_LOCATION, MAX_ID_LOCATION + 1) if i not in used_ids
        ]

        if not available_ids:
            return self.async_show_form(
                step_id="add_controller", errors={"base": "no_available_ids"}
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_ID_LOCATION): vol.In(
                    {
                        id_val: f"ID {id_val}"
                        for id_val in available_ids[:10]  # Show first 10
                    }
                ),
                vol.Required(CONF_CONTROLLER_TYPE): vol.In(
                    {
                        CONTROLLER_TYPE_ONOFF: "ON/OFF Controller (4 buttons)",
                        CONTROLLER_TYPE_DIMMER: "Dimmer Controller (7 buttons)",
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="add_controller",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_learn_buttons(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Learn button commands."""
        if not self._learning_id or not self._learning_type:
            return await self.async_step_init()

        # Get button definitions
        buttons = (
            DIMMER_BUTTONS
            if self._learning_type == CONTROLLER_TYPE_DIMMER
            else ONOFF_BUTTONS
        )

        if user_input is not None:
            if user_input.get("learn_button"):
                # Perform learning
                try:
                    await self._learn_button(self._learning_id, self._current_button)
                    self._learning_buttons[self._current_button] = True
                except BromicLearningError as err:
                    return self.async_show_form(
                        step_id="learn_buttons",
                        errors={"base": "learning_failed"},
                        description_placeholders={
                            "error": str(err),
                            "button_name": buttons[self._current_button]["name"],
                            "button_number": str(self._current_button),
                            "id_location": str(self._learning_id),
                        },
                    )

            if user_input.get("skip_button"):
                self._learning_buttons[self._current_button] = False

            # Move to next button
            self._current_button += 1

            # Check if we're done
            if self._current_button > len(buttons):
                return await self._finish_learning()

        # Show current button learning form
        button_info = buttons[self._current_button]
        learned_count = sum(self._learning_buttons.values())

        schema = vol.Schema(
            {
                vol.Optional("learn_button", default=False): bool,
                vol.Optional("skip_button", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="learn_buttons",
            data_schema=schema,
            description_placeholders={
                "button_name": button_info["name"],
                "button_number": str(self._current_button),
                "id_location": str(self._learning_id),
                "learned_count": str(learned_count),
                "total_buttons": str(len(buttons)),
                "controller_type": (
                    "Dimmer"
                    if self._learning_type == CONTROLLER_TYPE_DIMMER
                    else "ON/OFF"
                ),
            },
        )

    async def _learn_button(self, id_location: int, button: int) -> None:
        """Learn a specific button."""
        # Get hub from integration data
        hub_data = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if not hub_data:
            message = "Integration not initialized"
            raise BromicLearningError(message)

        hub: BromicHub = hub_data["hub"]

        if not hub.connected:
            message = "Device not connected"
            raise BromicLearningError(message)

        try:
            # Send learning command
            response = await hub.async_send_command(id_location, button)
        except Exception as err:
            _LOGGER.exception(
                "Learning failed for ID %d, Button %d", id_location, button
            )
            message = f"Learning failed: {err}"
            raise BromicLearningError(message) from err
        if not response.success:
            message = f"Learning failed: {response.message}"
            raise BromicLearningError(message)

    async def _finish_learning(self) -> FlowResult:
        """Finish the learning process and save configuration."""
        if not self._learning_id or not self._learning_type:
            return await self.async_step_init()

        # Update options
        controllers = self.config_entry.options.get(CONF_CONTROLLERS, {}).copy()
        controllers[str(self._learning_id)] = {
            CONF_CONTROLLER_TYPE: self._learning_type,
            CONF_LEARNED_BUTTONS: self._learning_buttons,
        }

        new_options = self.config_entry.options.copy()
        new_options[CONF_CONTROLLERS] = controllers

        # Reload the integration to create new entities
        self.hass.async_create_task(
            self.hass.config_entries.async_reload(self.config_entry.entry_id)
        )

        return self.async_create_entry(
            title="",
            data=new_options,
        )

    async def async_step_manage_controllers(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage existing controllers."""
        controllers = self.config_entry.options.get(CONF_CONTROLLERS, {})

        if not controllers:
            return self.async_show_form(
                step_id="manage_controllers", errors={"base": "no_controllers"}
            )

        if user_input is not None:
            controller_id = user_input["controller_id"]
            action = user_input["action"]

            if action == "delete":
                # Remove controller
                new_controllers = controllers.copy()
                del new_controllers[controller_id]

                new_options = self.config_entry.options.copy()
                new_options[CONF_CONTROLLERS] = new_controllers

                # Reload integration
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )

                return self.async_create_entry(title="", data=new_options)

        # Create controller list
        controller_options = {}
        for id_str, controller_info in controllers.items():
            controller_type = controller_info[CONF_CONTROLLER_TYPE]
            type_name = (
                "Dimmer" if controller_type == CONTROLLER_TYPE_DIMMER else "ON/OFF"
            )
            learned_buttons = controller_info.get(CONF_LEARNED_BUTTONS, {})
            learned_count = sum(learned_buttons.values())

            controller_options[id_str] = (
                f"ID {id_str} ({type_name}) - {learned_count} buttons"
            )

        schema = vol.Schema(
            {
                vol.Required("controller_id"): vol.In(controller_options),
                vol.Required("action"): vol.In(
                    {
                        "delete": "Delete Controller",
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="manage_controllers",
            data_schema=schema,
        )

    async def async_step_advanced_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure advanced settings."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=vol.Schema({}),  # Add advanced settings here if needed
        )

    async def async_step_change_serial_port(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Change the serial port for the hub without re-adding the integration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate by attempting a quick connection
            new_port = user_input[CONF_SERIAL_PORT]
            hub = BromicHub(self.hass, new_port)
            try:
                await hub.async_connect()
                await hub.async_test_connection()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Port validation failed for %s", new_port)
                errors["base"] = "cannot_connect"
            else:
                await hub.async_disconnect()

                # Persist to options
                new_options = self.config_entry.options.copy()
                new_options[CONF_SERIAL_PORT] = new_port

                # Reload integration to apply new port
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )

                return self.async_create_entry(title="", data=new_options)

        # Offer discovered ports if we have them
        discovered = await BromicHub.discover_ports()
        if discovered:
            port_options = {
                port["device"]: f"{port['device']} - {port['description']}"
                for port in discovered
            }
            schema = vol.Schema({vol.Required(CONF_SERIAL_PORT): vol.In(port_options)})
        else:
            schema = vol.Schema({vol.Required(CONF_SERIAL_PORT): str})

        return self.async_show_form(
            step_id="change_serial_port",
            data_schema=schema,
            errors=errors,
        )


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""
