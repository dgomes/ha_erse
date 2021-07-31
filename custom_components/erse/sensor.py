"""
Component to track electricity tariff.

For more details about this component, please refer to the documentation
at http://github.com/dgomes/home-assistant-custom-components/electricity/
"""
import logging

from electricity.tariffs import Operators
import voluptuous as vol

from homeassistant.components.utility_meter.const import (
    ATTR_TARIFF,
    DOMAIN as UTILITY_METER_DOMAIN,
    SERVICE_SELECT_TARIFF,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import (
    async_track_state_change_event,
)
from homeassistant.components.sensor import (
    DEVICE_CLASS_MONETARY,
    ATTR_LAST_RESET,
    STATE_CLASS_MEASUREMENT
)
from homeassistant.const import (
    CURRENCY_EURO
)


from .const import (
    CONF_COST,
    CONF_POWER_COST,
    DOMAIN,
    CONF_OPERATOR,
    CONF_PLAN,
    CONF_UTILITY_METER,
    CONF_UTILITY_METERS,
    COUNTRY,
)

_LOGGER = logging.getLogger(__name__)

ATTR_TARIFFS = "tariffs"
ATTR_UTILITY_METERS = "utility meters"

ICON = "mdi:transmission-tower"

UTILITY_METER_NAME_FORMAT = "{} {}"

IVA = 0.23
TERMO_FIXO_ACESSO_REDES = 0.2959

DISCOUNT = {
    "Vazio": (40, 0.13),
    "Fora de Vazio": (60, 0.13),
    "Normal": (100, 0.13)
}

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_OPERATOR): vol.In(Operators[COUNTRY].keys()),
        vol.Required(CONF_PLAN): vol.In(
            list(
                {
                    str(p)
                    for plans in Operators[COUNTRY].values()
                    for p in plans.tariff_periods()
                }
            )
        ),
        vol.Required(CONF_UTILITY_METERS): vol.All(cv.ensure_list, [cv.string]),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up an electricity monitor."""

    async_add_entities([EletricityEntity(config[CONF_OPERATOR], config)])


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up an electricity monitor from a Config Entry."""

    entities = [EletricityEntity(config_entry.title, config_entry.data)]

    for utility_meter in config_entry.data[CONF_UTILITY_METER]:
        meter_entity_template = f"{utility_meter[14:]}"


        for tariff, cost in config_entry.data[CONF_COST].items():
            meter_entity = "sensor." + slugify(f"{meter_entity_template} {tariff}")


            entities.append(TariffCost(*DISCOUNT[tariff], meter_entity, cost))
        else:
            entities.append(FixedCost(config_entry.data[CONF_OPERATOR], config_entry.data[CONF_PLAN], meter_entity, config_entry.data[CONF_POWER_COST]))


    async_add_entities(entities)


class TariffCost(SensorEntity):
    """Track cost of kWh for a given tariff"""

    def __init__(self, discount_kwh, discount_iva, meter_entity, kwh_cost):
        """Initialize cost tracker"""
        self._attr_name = f"{meter_entity} cost"
        self._kwh_cost = kwh_cost
        self._meter_entity = meter_entity
        self._cost = 0
        self._discount_kwh = discount_kwh
        self._discount_iva = discount_iva
        self._attr_device_class = DEVICE_CLASS_MONETARY
        self._attr_unique_id = slugify(meter_entity + "cost")
        self._attr_unit_of_measurement = CURRENCY_EURO
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_last_reset = dt_util.utc_from_timestamp(0) #TODO actually reset

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        @callback
        async def async_increment_cost(event):
            new_state = event.data.get("new_state")
            calc_costs(new_state.state)

        def calc_costs(kwh):
            kwh = float(kwh)

            if kwh == 0:
                self._attr_last_reset = dt_util.now()

            total = 0
            if kwh > self._discount_kwh:
                total += float(self._kwh_cost) * (float(kwh)-self._discount_kwh) * (1+IVA)
                kwh = self._discount_kwh
            total += float(self._kwh_cost) * float(kwh) * (1+self._discount_iva)

            self._attr_state = total


        async_track_state_change_event(
            self.hass, [self._meter_entity], async_increment_cost
        )

        meter_state = self.hass.states.get(self._meter_entity)
        if meter_state:
            calc_costs(meter_state.state)

class FixedCost(SensorEntity):
    """Track fixed costs."""
    def __init__(self, operator, plan, meter, power_cost) -> None:
        """Initialize fixed costs"""
        self._attr_name = f"{plan} cost"
        self._attr_device_class = DEVICE_CLASS_MONETARY
        self._attr_unique_id = slugify(f"{operator} {plan} cost")
        self._attr_unit_of_measurement = CURRENCY_EURO
        self._meter = meter
        self._power_cost = power_cost
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_last_reset = dt_util.utc_from_timestamp(0) #TODO actually reset


    async def async_added_to_hass(self):
        """Setups all required entities and automations."""
        async_track_time_change(self.hass, self.timer_update, hour=[0], minute=[0], second=[0])

        @callback
        async def initial_sync(event):
            await self.timer_update(dt_util.now())

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

    @callback
    async def timer_update(self, now):
        """Change tariff based on timer."""

        last_reset = self.hass.states.get(self._meter).attributes[ATTR_LAST_RESET]
        last_reset = dt_util.parse_datetime(last_reset)

        elapsed = now - last_reset
        if elapsed.days == 0:
            self._attr_last_reset = now

        self._attr_state = (elapsed.days+1) * (TERMO_FIXO_ACESSO_REDES + self._power_cost)

class EletricityEntity(Entity):
    """Representation of an Electricity Contract."""

    def __init__(self, name, config):
        """Initialize an Electricity Contract."""
        self._attr_name = name
        self.operator = config[CONF_OPERATOR]
        self.plan = config[CONF_PLAN]
        self.utility_meters = config[CONF_UTILITY_METER]
        self.my_plan = Operators[COUNTRY][self.operator](plan=self.plan)
        self._tariffs = self.my_plan.tariffs()
        self._state = None
        self._attr_icon = ICON
        self._attr_unique_id = slugify(
            str(self.operator) + str(self.plan) + str(len(self.utility_meters))
        )

    async def async_added_to_hass(self):
        """Setups all required entities and automations."""
        async_track_time_change(self.hass, self.timer_update, minute=range(0, 60, 15))

        @callback
        async def initial_sync(event):
            await self.timer_update(dt_util.now())

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

    @callback
    async def timer_update(self, now):
        """Change tariff based on timer."""

        new_state = self.my_plan.current_tariff(now)

        if new_state != self._state:
            _LOGGER.debug("Changing from %s to %s", self._state, new_state)
            self._state = new_state

            await self.async_update_ha_state()

            for utility_meter in self.utility_meters:
                _LOGGER.debug("Change %s to %s", utility_meter, self._state)
                await self.hass.services.async_call(
                    UTILITY_METER_DOMAIN,
                    SERVICE_SELECT_TARIFF,
                    {ATTR_ENTITY_ID: utility_meter, ATTR_TARIFF: self._state},
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
        attr = dict()
        if self._tariffs:
            attr[ATTR_TARIFFS] = self._tariffs
        attr[ATTR_UTILITY_METERS] = self.utility_meters
        return attr