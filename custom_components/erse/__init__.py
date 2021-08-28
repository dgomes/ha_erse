"""The Entidade Reguladora dos Serviços Energéticos integration."""
import asyncio
import logging

from pyerse.comercializador import Comercializador, Tarifa
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.components import persistent_notification

from homeassistant.components.sensor import ATTR_LAST_RESET
from pyerse.simulador import Simulador
from pyerse.comercializador import Tarifa, Opcao_Horaria

from .const import (
    CONF_POWER_COST,
    DOMAIN,
    CONF_CYCLE,
    CONF_INSTALLED_POWER,
    CONF_PLAN,
    CONF_OPERATOR,
    CONF_METER_SUFFIX,
)

# CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["sensor"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Entidade Reguladora dos Serviços Energéticos component."""
    return True


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
        data = {}
        for tariff in hass.data[DOMAIN][entry.entry_id].plano.tarifas:
            for meter_entity in entry.data[f"{tariff.name}{CONF_METER_SUFFIX}"]:
                data[tariff] = int(float(hass.states.get(meter_entity).state))
                last_reset = hass.states.get(meter_entity).attributes[ATTR_LAST_RESET]
                last_reset = dt_util.parse_datetime(last_reset).strftime("%Y-%m-%d")

        potencia = entry.data[CONF_INSTALLED_POWER]

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

        if Tarifa.PONTA in data:
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

        if Tarifa.FORA_DE_VAZIO in data or Tarifa.PONTA in data:
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

    hass.services.async_register(DOMAIN, "simular", async_simular)

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
