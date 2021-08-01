"""Config flow for Entidade Reguladora dos Serviços Energéticos integration."""
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from pyerse.ciclos import Ciclo, Ciclo_Semanal, Ciclo_Diario
from pyerse.comercializador import Plano, Opcao_Horaria, PlanoException, Tarifa, Comercializador 

from homeassistant import config_entries, core, exceptions
from homeassistant.util import slugify

from .const import (
    CONF_COST,
    CONF_OPERATOR,
    CONF_INSTALLED_POWER,
    CONF_PLAN,
    CONF_CYCLE,
    CONF_POWER_COST,
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
    CONNECTION_CLASS = config_entries.CONN_CLASS_ASSUMED

    async def async_step_user(self, user_input=None):
        """Handle electrical energy plan configuration."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_OPERATOR): str,
                        vol.Required(CONF_INSTALLED_POWER): vol.In(Comercializador.potencias()),
                        vol.Required(CONF_PLAN): vol.In(Comercializador.opcao_horaria()),
                        vol.Required(CONF_CYCLE, default="Ciclo Diário"): vol.In(Comercializador.opcao_ciclo())
                    }
                ),
            )

        try:
            self.operator = Comercializador(user_input[CONF_OPERATOR], user_input[CONF_INSTALLED_POWER], user_input[CONF_PLAN], user_input[CONF_CYCLE])
        except Exception:
            #TODO do something about it
            pass

        self.info = user_input
        return await self.async_step_utility_meter()

    async def async_step_utility_meter(self, user_input=None):
        """Handle the choice of the utility meter."""
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="utility_meter",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_UTILITY_METER): cv.multi_select(
                            [
                                s.entity_id
                                for s in self.hass.states.async_all()
                                if s.domain == "utility_meter"
                            ]
                        ),
                    }
                ),
            )

        self.info[CONF_UTILITY_METER] = user_input[CONF_UTILITY_METER]
        return await self.async_step_costs()

    async def async_step_costs(self, user_input=None):
        """Handle the costs of each tariff."""
        errors = {}

        if user_input is None:
            DATA_SCHEMA = vol.Schema(
                {
                    **{vol.Required(CONF_POWER_COST): float},
                    **{vol.Required(str(tariff)): float for tariff in self.operator.plano.tarifas},
                }
            )
            return self.async_show_form(
                step_id="costs", data_schema=DATA_SCHEMA, errors=errors
            )

        try:
            for key in user_input:
                if key == CONF_POWER_COST:
                    self.operator.plano.definir_custo_potencia(user_input[key])
                else:
                    self.operator.plano.definir_custo_kWh(key, user_input[key])
        except Exception:
            #TODO do something about it
            pass

        return self.async_create_entry(
            title=str(self.operator),
            data={ **self.info, **user_input }
        )