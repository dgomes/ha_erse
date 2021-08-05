"""The Entidade Reguladora dos Serviços Energéticos integration."""
from pyerse.comercializador import Comercializador, Tarifa
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_POWER_COST,
    DOMAIN,
    CONF_CYCLE,
    CONF_INSTALLED_POWER,
    CONF_PLAN,
    CONF_OPERATOR,
    UPDATE_LISTENER,
)

# CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["sensor"]


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
