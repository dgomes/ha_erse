"""
Component to track electricity tariff.

For more details about this component, please refer to the documentation
at http://github.com/dgomes/home-assistant-custom-components/electricity/
"""
import logging

from homeassistant.components.sensor import (
    ATTR_LAST_RESET,
    DEVICE_CLASS_MONETARY,
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
)
from homeassistant.components.utility_meter.const import ATTR_TARIFF
from homeassistant.components.utility_meter.const import DOMAIN as UTILITY_METER_DOMAIN
from homeassistant.components.utility_meter.const import SERVICE_SELECT_TARIFF
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CURRENCY_EURO,
    EVENT_HOMEASSISTANT_START,
    ATTR_UNIT_OF_MEASUREMENT,
    ENERGY_WATT_HOUR,
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    CONF_METER_SUFFIX,
    CONF_UTILITY_METER,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ATTR_TARIFFS = "tariffs"
ATTR_UTILITY_METER = "utility meter"

ICON = "mdi:transmission-tower"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up an electricity monitor from a Config Entry."""

    #import pprint
    #pprint.pprint(config_entry.data)

    entities = list()

    if CONF_UTILITY_METER in config_entry.data:
        entities.append(
            EletricityEntity(
                hass, config_entry.entry_id, config_entry.data[CONF_UTILITY_METER]
            )
        )

    for tariff in hass.data[DOMAIN][config_entry.entry_id].plano.tarifas:
        meter_entity = config_entry.data[f"{tariff.name}{CONF_METER_SUFFIX}"]

        entities.append(TariffCost(hass, config_entry.entry_id, tariff, meter_entity))

    entities.append(FixedCost(hass, config_entry.entry_id, meter_entity))

    async_add_entities(entities)


class TariffCost(SensorEntity):
    """Track cost of kWh for a given tariff"""

    def __init__(self, hass, entry_id, tariff, meter_entity):
        """Initialize cost tracker"""
        self.operator = hass.data[DOMAIN][entry_id]

        self._attr_device_class = DEVICE_CLASS_MONETARY
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_unit_of_measurement = CURRENCY_EURO
        self._attr_last_reset = dt_util.utc_from_timestamp(0)

        self._attr_name = f"{self.operator} {tariff} cost"
        self._attr_unique_id = slugify(f"{entry_id} {tariff} cost")

        self._tariff = tariff
        self._meter_entity = meter_entity

    async def async_added_to_hass(self):
        """Handle entity which will be tracked."""
        await super().async_added_to_hass()

        def calc_costs(meter_state):

            if meter_state and meter_state.attributes[ATTR_UNIT_OF_MEASUREMENT] in [
                ENERGY_WATT_HOUR,
                ENERGY_KILO_WATT_HOUR,
            ]:
                if meter_state.attributes[ATTR_UNIT_OF_MEASUREMENT] == ENERGY_WATT_HOUR:
                    kwh = float(meter_state.state) / 1000
                else:
                    kwh = float(meter_state.state)
            else:
                _LOGGER.error(
                    "Could not retrieve tariff sensor state or the sensor is not an energy sensor (wrong unit)"
                )
                kwh = 0

            self._attr_state = self.operator.plano.custo_kWh_final(self._tariff, kwh)

            _LOGGER.debug(
                "{%s} calc_costs(%s) = %s using %s",
                self._attr_name,
                kwh,
                self._attr_state,
                self.operator.plano._custo,
            )

        @callback
        async def async_increment_cost(event):
            new_state = event.data.get("new_state")
            calc_costs(new_state)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._meter_entity], async_increment_cost
            )
        )

        @callback
        async def initial_sync(event):
            meter_state = self.hass.states.get(self._meter_entity)
            calc_costs(meter_state)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)


class FixedCost(SensorEntity):
    """Track fixed costs."""

    def __init__(self, hass, entry_id, any_meter) -> None:
        """Initialize fixed costs"""
        self.operator = hass.data[DOMAIN][entry_id]

        self._attr_device_class = DEVICE_CLASS_MONETARY
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_unit_of_measurement = CURRENCY_EURO
        self._attr_last_reset = dt_util.utc_from_timestamp(0)

        self._attr_name = f"{self.operator} cost"
        self._attr_unique_id = slugify(f"{entry_id} fixed cost")

        self._meter = any_meter

    async def async_added_to_hass(self):
        """Setups automations."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_track_time_change(
                self.hass, self.timer_update, hour=[0], minute=[0], second=[0]
            )
        )

        @callback
        async def initial_sync(event):
            await self.timer_update(dt_util.now())

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

    @callback
    async def timer_update(self, now):
        """Update fixed costs as days go by."""

        last_reset = self.hass.states.get(self._meter).attributes[ATTR_LAST_RESET]
        last_reset = dt_util.parse_datetime(last_reset)

        elapsed = now - last_reset
        if elapsed.days == 0:
            self._attr_last_reset = now

        self._attr_state = self.operator.plano.custos_fixos(elapsed.days)


class EletricityEntity(Entity):
    """Representation of an Electricity Tariff tracker."""

    def __init__(self, hass, entry_id, utility_meter):
        """Initialize an Electricity Tariff Tracker."""
        self.operator = hass.data[DOMAIN][entry_id]
        self._attr_name = str(self.operator)
        self.utility_meter = utility_meter
        self._state = None
        self._attr_icon = ICON
        self._attr_unique_id = slugify(f"{entry_id} {self.utility_meter}")

    async def async_added_to_hass(self):
        """Setups all required entities and automations."""

        self.async_on_remove(
            async_track_time_change(
                self.hass, self.timer_update, minute=range(0, 60, 15)
            )
        )

        @callback
        async def initial_sync(event):
            await self.timer_update(dt_util.now())

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

    @callback
    async def timer_update(self, now):
        """Change tariff based on timer."""

        new_state = self.operator.plano.tarifa_actual().value

        if new_state != self._state:
            _LOGGER.debug("Changing from %s to %s", self._state, new_state)
            self._state = new_state

            await self.async_update_ha_state()

            _LOGGER.debug("Change %s to %s", self.utility_meter, self._state)
            await self.hass.services.async_call(
                UTILITY_METER_DOMAIN,
                SERVICE_SELECT_TARIFF,
                {ATTR_ENTITY_ID: self.utility_meter, ATTR_TARIFF: self._state},
            )

    @property
    def should_poll(self):
        """If entity should be polled."""
        return False

    @property
    def state(self):
        """Return the state as the current tariff."""
        return self._state

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attr = {
            ATTR_TARIFFS: self.operator.plano.tarifas,
            ATTR_UTILITY_METER: self.utility_meter,
        }
        return attr
