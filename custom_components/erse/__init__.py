"""The Entidade Reguladora dos Serviços Energéticos integration."""
import asyncio
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.components.sensor import ATTR_LAST_RESET
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pyerse.comercializador import POTENCIA, Comercializador, Opcao_Horaria, Tarifa
from pyerse.simulador import Simulador

from .const import (
    CONF_CHEIAS,
    CONF_CYCLE,
    CONF_FORA_DE_VAZIO,
    CONF_INSTALLED_POWER,
    CONF_NORMAL,
    CONF_OPERATOR,
    CONF_PLAN,
    CONF_PONTA,
    CONF_POWER_COST,
    CONF_VAZIO,
    DOMAIN,
)

PLATFORMS = ["sensor"]

_LOGGER = logging.getLogger(__name__)


def valid_plan(config):
    # Tri-Horario
    if (
        CONF_PONTA in config
        and CONF_CHEIAS in config
        and CONF_VAZIO in config
        and CONF_NORMAL not in config
        and CONF_FORA_DE_VAZIO not in config
    ):
        return config

    # Bi-Horario
    if (
        CONF_PONTA not in config
        and CONF_CHEIAS not in config
        and CONF_VAZIO in config
        and CONF_NORMAL not in config
        and CONF_FORA_DE_VAZIO in config
    ):
        return config

    # Normal
    if (
        CONF_PONTA not in config
        and CONF_CHEIAS not in config
        and CONF_VAZIO not in config
        and CONF_NORMAL in config
        and CONF_FORA_DE_VAZIO not in config
    ):
        return config
    raise vol.Invalid(
        f"You must choose only the sensors relevant to you current plan (Tri-Horario, Bi-Horario, Normal)"
    )


SIMUL_SCHEMA = vol.Schema(
    vol.All(
        {
            vol.Required(CONF_INSTALLED_POWER): vol.In(POTENCIA),
            vol.Optional(CONF_PONTA): cv.entity_id,
            vol.Optional(CONF_CHEIAS): cv.entity_id,
            vol.Optional(CONF_VAZIO): cv.entity_id,
            vol.Optional(CONF_FORA_DE_VAZIO): cv.entity_id,
            vol.Optional(CONF_NORMAL): cv.entity_id,
        },
        valid_plan,
    )
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Entidade Reguladora dos Serviços Energéticos from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    operador = Comercializador(
        entry.data[CONF_OPERATOR],
        entry.data[CONF_INSTALLED_POWER],
        entry.data[CONF_PLAN],
        entry.data[CONF_CYCLE],
    )

    costs = entry.options if entry.options else entry.data

    for tariff in operador.plano.tarifas:
        operador.plano.definir_custo_kWh(Tarifa(tariff), costs[tariff.name])
    operador.plano.definir_custo_potencia(costs[CONF_POWER_COST])

    hass.data[DOMAIN][entry.entry_id] = operador

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    async def async_simular(service):
        data = {
            Tarifa.PONTA: service.data.get(CONF_PONTA),
            Tarifa.CHEIAS: service.data.get(CONF_CHEIAS),
            Tarifa.VAZIO: service.data.get(CONF_VAZIO),
            Tarifa.FORA_DE_VAZIO: service.data.get(CONF_FORA_DE_VAZIO),
            Tarifa.NORMAL: service.data.get(CONF_NORMAL),
        }

        data = {
            tarif: int(float(hass.states.get(meter_entity).state))
            for tarif, meter_entity in data.items()
            if meter_entity is not None
        }

        for meter in [CONF_PONTA, CONF_FORA_DE_VAZIO, CONF_NORMAL]:
            if service.data.get(meter) is not None:
                last_reset = hass.states.get(service.data.get(meter)).attributes[
                    ATTR_LAST_RESET
                ]
                last_reset = dt_util.parse_datetime(last_reset).strftime("%Y-%m-%d")

        potencia = service.data[CONF_INSTALLED_POWER]

        _LOGGER.debug(
            "Simular potencia de %s, desde dia %s, com valores %s",
            potencia,
            last_reset,
            data,
        )
        simulador = Simulador(potencia, last_reset)

        _LOGGER.debug("simular simples")
        simulacoes = [
            (
                Opcao_Horaria.SIMPLES,
                await hass.async_add_executor_job(
                    simulador.melhor_tarifa_simples, sum(data.values())
                ),
            )
        ]  # Simples

        if Tarifa.PONTA in data:
            _LOGGER.debug("simular tri-horario")
            simulacoes.append(
                (
                    Opcao_Horaria.TRI_HORARIA,
                    await hass.async_add_executor_job(
                        simulador.melhor_tarifa_trihorario,
                        data[Tarifa.PONTA],
                        data[Tarifa.CHEIAS],
                        data[Tarifa.VAZIO],
                    ),
                )
            )
            _LOGGER.debug("simular downgrade para bi-horario")
            simulacoes.append(
                (
                    Opcao_Horaria.BI_HORARIA,
                    await hass.async_add_executor_job(
                        simulador.melhor_tarifa_bihorario,
                        data[Tarifa.PONTA] + data[Tarifa.CHEIAS],
                        data[Tarifa.VAZIO],
                    ),
                )
            )

        if Tarifa.FORA_DE_VAZIO in data:
            _LOGGER.debug("simular bi-horario")
            simulacoes.append(
                (
                    Opcao_Horaria.BI_HORARIA,
                    await hass.async_add_executor_job(
                        simulador.melhor_tarifa_bihorario,
                        data[Tarifa.FORA_DE_VAZIO],
                        data[Tarifa.VAZIO],
                    ),
                )
            )

        _LOGGER.debug(simulacoes)

        opcao_horaria, (melhor_plano, estimativa) = min(
            simulacoes, key=lambda a: a[1][1]
        )

        persistent_notification.async_create(
            hass,
            f"De acordo com o simulador da ERSE o melhor plano com base nos consumos actuais é o <{melhor_plano}> em opção {opcao_horaria}, estaria a pagar custos fixos + energia {round(estimativa,2)} €. Por favor confirme este valor em https://simulador.precos.erse.pt/eletricidade/",
            "Simulador ERSE",
        )

    hass.services.async_register(DOMAIN, "simular", async_simular, schema=SIMUL_SCHEMA)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update options."""
    operador = hass.data[DOMAIN][config_entry.entry_id]

    for tariff in operador.plano.tarifas:
        operador.plano.definir_custo_kWh(
            Tarifa(tariff), config_entry.options[tariff.name]
        )
    operador.plano.definir_custo_potencia(config_entry.options[CONF_POWER_COST])


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )

    return unload_ok
