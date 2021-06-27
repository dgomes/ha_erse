"""Config flow for Entidade Reguladora dos Serviços Energéticos integration."""
import logging

from electricity.tariffs import Operators
import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.util import slugify
import homeassistant.helpers.config_validation as cv

from .const import (  # pylint:disable=unused-import
    CONF_COST_POTENCIA,
    CONF_OPERATOR,
    CONF_PLAN,
    CONF_UTILITY_METERS,
    COUNTRY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Entidade Reguladora dos Serviços Energéticos."""

    VERSION = 1
    # TODO pick one of the available connection classes in homeassistant/config_entries.py
    CONNECTION_CLASS = config_entries.CONN_CLASS_UNKNOWN

    async def async_step_user(self, user_input=None):
        """Handle choice of operator."""
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
        return await self.async_step_plan()

    async def async_step_plan(self, user_input=None):
        """Handle choice of plan step."""
        if user_input is None:

            DATA_SCHEMA = vol.Schema(
                {
                    vol.Required(CONF_PLAN): vol.In(
                        list(
                            {
                                str(p)
                                for p in Operators[COUNTRY][
                                    self.operator
                                ].tariff_periods()
                            }
                        )
                    ),
                }
            )

            return self.async_show_form(step_id="plan", data_schema=DATA_SCHEMA)
        print(user_input)
        self.plan = user_input[CONF_PLAN]
        return await self.async_step_cost()

    async def async_step_cost(self, user_input=None):
        """insert costs."""
        errors = {}

        if user_input is not None:
            try:
                user_input[CONF_OPERATOR] = self.operator
                user_input[CONF_PLAN] = self.plan

                #TODO validate utility_meter has matching tariffs

                return self.async_create_entry(
                    title=slugify(
                        f"{user_input[CONF_OPERATOR]} - {user_input[CONF_PLAN]}"
                    ),
                    data=user_input,
                )

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        my_plan = Operators[COUNTRY][self.operator](plan=self.plan)
        tariffs = my_plan.tariffs() if isinstance(my_plan.tariffs(), list) else [my_plan.tariffs()] #TODO change this upstream

        DATA_SCHEMA = vol.Schema(
            {
                **{
                    vol.Required(CONF_UTILITY_METERS): cv.multi_select(
                        [
                            s.entity_id
                            for s in self.hass.states.async_all()
                            if s.domain == "utility_meter"
                        ]
                    ),
                    vol.Required(CONF_COST_POTENCIA): float,
                },
                **{
                    vol.Required(slugify("cost_" + tariff)): float
                    for tariff in tariffs
                },
            }
        )

        print(DATA_SCHEMA)

        return self.async_show_form(
            step_id="cost", data_schema=DATA_SCHEMA, errors=errors
        )

