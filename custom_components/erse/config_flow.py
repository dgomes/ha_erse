"""Config flow for Entidade Reguladora dos Serviços Energéticos integration."""
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import callback
from homeassistant.helpers import selector
from pyerse.ciclos import Ciclo_Diario
from pyerse.comercializador import POTENCIA, Comercializador

from .const import (
    CONF_CYCLE,
    CONF_INSTALLED_POWER,
    CONF_METER_SUFFIX,
    CONF_OPERATOR,
    CONF_PLAN,
    CONF_POWER_COST,
    CONF_UTILITY_METERS,
    CONF_EXPORT_METER,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

POTENCIAS = [
    {"value": str(p), "label": f"{p} kVA"} for p in Comercializador.potencias()
]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Entidade Reguladora dos Serviços Energéticos."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_ASSUMED

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return ERSEOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle electrical energy plan configuration."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_OPERATOR): str,
                        vol.Required(
                            CONF_INSTALLED_POWER, default=str(POTENCIA[0])
                        ): selector.selector({"select": {"options": POTENCIAS}}),
                        vol.Required(CONF_PLAN): vol.In(
                            Comercializador.opcao_horaria()
                        ),
                        vol.Required(CONF_CYCLE, default=str(Ciclo_Diario())): vol.In(
                            Comercializador.opcao_ciclo()
                        ),
                    }
                ),
            )

        user_input[CONF_INSTALLED_POWER] = float(user_input[CONF_INSTALLED_POWER])
        try:
            self.operator = Comercializador(
                user_input[CONF_OPERATOR],
                user_input[CONF_INSTALLED_POWER],
                user_input[CONF_PLAN],
                user_input[CONF_CYCLE],
            )
        except Exception:
            # TODO do something about it
            pass

        self.info = user_input
        return await self.async_step_utility_meter()

    async def async_step_utility_meter(self, user_input=None):
        """Handle the choice of the utility meter."""

        if user_input is None:
            return self.async_show_form(
                step_id="utility_meter",
                data_schema=vol.Schema(
                    {
                        vol.Optional(CONF_UTILITY_METERS): selector.selector(
                            {
                                "entity": {
                                    "domain": "select",
                                    "integration": "utility_meter",
                                    "multiple": True,
                                }
                            },
                        ),
                        vol.Optional(CONF_EXPORT_METER): selector.selector(
                            {
                                "entity": {
                                    "domain": SENSOR_DOMAIN,
                                    "device_class": "energy",
                                }
                            },
                        ),
                    }
                ),
            )

        if CONF_UTILITY_METERS in user_input:
            self.info[CONF_UTILITY_METERS] = user_input[CONF_UTILITY_METERS]
        if CONF_EXPORT_METER in user_input:
            self.info[CONF_EXPORT_METER] = user_input[CONF_EXPORT_METER]
        return await self.async_step_costs()

    async def async_step_costs(self, user_input=None):
        """Handle the costs of each tariff."""
        errors = {}

        if user_input is None:
            DATA_SCHEMA = vol.Schema(
                {
                    vol.Required(CONF_POWER_COST): vol.Coerce(float),
                    **{
                        vol.Required(tariff.name): vol.Coerce(float)
                        for tariff in self.operator.plano.tarifas
                    },
                    **{
                        vol.Required(
                            tariff.name + CONF_METER_SUFFIX
                        ): selector.selector(
                            {
                                "entity": {
                                    "domain": "sensor",
                                    "device_class": "energy",
                                    "integration": "utility_meter",
                                    "multiple": True,
                                }
                            },
                        )
                        for tariff in self.operator.plano.tarifas
                    },
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
            # TODO do something about it
            pass

        return self.async_create_entry(
            title=str(self.operator), data={**self.info, **user_input}
        )


class ERSEOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""

        self.operator = Comercializador(
            config_entry.data[CONF_OPERATOR],
            float(config_entry.data[CONF_INSTALLED_POWER]),
            config_entry.data[CONF_PLAN],
            config_entry.data[CONF_CYCLE],
        )
        self.costs = {
            CONF_POWER_COST: config_entry.options.get(
                CONF_POWER_COST, config_entry.data[CONF_POWER_COST]
            ),
            **{
                tariff.name: config_entry.options.get(
                    tariff.name, config_entry.data[tariff.name]
                )
                for tariff in self.operator.plano.tarifas
            },
        }

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POWER_COST, default=self.costs[CONF_POWER_COST]
                    ): vol.Coerce(float),
                    **{
                        vol.Required(
                            tariff.name, default=self.costs[tariff.name]
                        ): vol.Coerce(float)
                        for tariff in self.operator.plano.tarifas
                    },
                }
            ),
        )
