"""Config flow for Entidade Reguladora dos Serviços Energéticos integration."""
import logging

from electricity.tariffs import Operators
import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.util import slugify
import homeassistant.helpers.config_validation as cv

from .const import (  # pylint:disable=unused-import
    CONF_OPERATOR,
    CONF_PLAN,
    CONF_UTILITY_METER,
    CONF_UTILITY_METERS,
    COUNTRY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: core.HomeAssistant, data):
    """Test if operator and plan are valid."""

    if data[CONF_PLAN] not in Operators[COUNTRY][data[CONF_OPERATOR]].tariff_periods():
        raise InvalidPlan

    return {
        CONF_OPERATOR: data[CONF_OPERATOR],
        CONF_PLAN: data[CONF_PLAN],
        CONF_UTILITY_METERS: [data[CONF_UTILITY_METER]],
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Entidade Reguladora dos Serviços Energéticos."""

    VERSION = 1
    # TODO pick one of the available connection classes in homeassistant/config_entries.py
    CONNECTION_CLASS = config_entries.CONN_CLASS_UNKNOWN


    async def async_step_user(self, user_input=None):
        """Handle choice of tarifario."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {                
                        vol.Required(CONF_OPERATOR): vol.In(Operators[COUNTRY].keys()),
                    }
                ),
            )
        
        self.operator = user_input[CONF_OPERATOR]
        return await self.async_step_finish()

    async def async_step_finish(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                user_input[CONF_OPERATOR] = self.operator
                info = await validate_input(self.hass, user_input)

                return self.async_create_entry(
                    title=slugify(
                        f"{info[CONF_OPERATOR]} - {info[CONF_PLAN]}"
                    ),
                    data=info,
                )
            except InvalidPlan:
                errors["plan"] = "invalid_plan"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_PLAN): vol.In(
                    list(
                        set(
                            [
                                str(p)
                                for p in Operators[COUNTRY][self.operator].tariff_periods()
                            ]
                        )
                    )
                ),
                vol.Required(CONF_UTILITY_METER): cv.multi_select(
                    [
                        s.entity_id
                        for s in self.hass.states.async_all()
                        if s.domain == "utility_meter"
                    ]
                ),
            }
        )

        return self.async_show_form(
            step_id="finish", data_schema=DATA_SCHEMA, errors=errors
        )


class InvalidPlan(exceptions.HomeAssistantError):
    """Error to indicate there is invalid plan."""
