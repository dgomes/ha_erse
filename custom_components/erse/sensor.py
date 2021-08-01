"""
Component to track electricity tariff.

For more details about this component, please refer to the documentation
at http://github.com/dgomes/home-assistant-custom-components/electricity/
"""
import logging

from electricity.tariffs import Operators
from homeassistant.components.sensor import (
    ATTR_LAST_RESET,
    DEVICE_CLASS_MONETARY,
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
)
from homeassistant.components.utility_meter.const import ATTR_TARIFF
from homeassistant.components.utility_meter.const import DOMAIN as UTILITY_METER_DOMAIN
from homeassistant.components.utility_meter.const import SERVICE_SELECT_TARIFF
from homeassistant.const import ATTR_ENTITY_ID, CURRENCY_EURO, EVENT_HOMEASSISTANT_START
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    CONF_COST,
    CONF_OPERATOR,
    CONF_PLAN,
    CONF_POWER_COST,
    CONF_UTILITY_METER,
    CONTRIB_AUDIOVISUAL,
    COUNTRY,
    DISCOUNT,
    IMPOSTO_ESPECIAL_DE_CONSUMO,
    IVA,
    IVA_REDUZIDA,
    TAXA_DGEG,
    TERMO_FIXO_ACESSO_REDES,
)

_LOGGER = logging.getLogger(__name__)

ATTR_TARIFFS = "tariffs"
ATTR_UTILITY_METERS = "utility meters"

ICON = "mdi:transmission-tower"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up an electricity monitor from a Config Entry."""

    entities = [EletricityEntity(config_entry.title, config_entry.data)]

    for utility_meter in config_entry.data[CONF_UTILITY_METER]:
        meter_entity_template = f"{utility_meter[14:]}"

        for tariff, cost in config_entry.data[CONF_COST].items():
            meter_entity = "sensor." + slugify(f"{meter_entity_template} {tariff}")

            entities.append(TariffCost(*DISCOUNT[tariff], meter_entity, cost))

        entities.append(
            FixedCost(
                config_entry.data[CONF_OPERATOR],
                config_entry.data[CONF_PLAN],
                meter_entity,
                config_entry.data[CONF_POWER_COST],
            )
        )

    async_add_entities(entities)


class TariffCost(SensorEntity):
    """Track cost of kWh for a given tariff"""

    def __init__(self, discount_kwh, discount_iva, meter_entity, kwh_cost):
        """Initialize cost tracker"""
        self._attr_device_class = DEVICE_CLASS_MONETARY
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_unit_of_measurement = CURRENCY_EURO
        self._attr_last_reset = dt_util.utc_from_timestamp(0)

        self._attr_name = f"{meter_entity} cost"
        self._attr_unique_id = slugify(meter_entity + "cost")

        self._discount_kwh = discount_kwh
        self._discount_iva = discount_iva
        self._meter_entity = meter_entity
        self._kwh_cost = kwh_cost

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        def calc_costs(kwh):
            kwh = float(kwh)

            _LOGGER.debug("{%s} calc_costs(%s)", self._attr_name, kwh)

            if kwh == 0:
                self._attr_last_reset = dt_util.now()

            total = kwh * IMPOSTO_ESPECIAL_DE_CONSUMO * (1 + IVA)
            if kwh > self._discount_kwh:
                total += (
                    float(self._kwh_cost)
                    * (float(kwh) - self._discount_kwh)
                    * (1 + IVA)
                )
                kwh = self._discount_kwh
            total += float(self._kwh_cost) * float(kwh) * (1 + self._discount_iva)

            self._attr_state = total

        @callback
        async def async_increment_cost(event):
            new_state = event.data.get("new_state")
            calc_costs(new_state.state)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._meter_entity], async_increment_cost
            )
        )

        @callback
        async def initial_sync(event):
            meter_state = self.hass.states.get(self._meter_entity)
            if meter_state:
                calc_costs(meter_state.state)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)


class FixedCost(SensorEntity):
    """Track fixed costs."""

    def __init__(self, operator, plan, meter, power_cost) -> None:
        """Initialize fixed costs"""
        self._attr_device_class = DEVICE_CLASS_MONETARY
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_last_reset = dt_util.utc_from_timestamp(0)

        self._attr_name = f"{operator} {plan} cost"
        self._attr_unique_id = slugify(f"{operator} {plan} cost")
        self._attr_unit_of_measurement = CURRENCY_EURO

        self._meter = meter
        self._power_cost = power_cost

    async def async_added_to_hass(self):
        """Setups all required entities and automations."""

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
        """Change tariff based on timer."""

        last_reset = self.hass.states.get(self._meter).attributes[ATTR_LAST_RESET]
        last_reset = dt_util.parse_datetime(last_reset)

        elapsed = now - last_reset
        if elapsed.days == 0:
            self._attr_last_reset = now

        self._attr_state = (
            (elapsed.days + 1) * (TERMO_FIXO_ACESSO_REDES + self._power_cost)
            + TAXA_DGEG
        ) * (1 + IVA) + CONTRIB_AUDIOVISUAL * (1 + IVA_REDUZIDA)


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
            f"{self.operator} {self.plan} {len(self.utility_meters)}"
        )

    async def async_added_to_hass(self):
        """Setups all required entities and automations."""

        self.async_on_remove(
            async_track_time_change(self.hass, self.timer_update, minute=range(0, 60, 15))
        )

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
