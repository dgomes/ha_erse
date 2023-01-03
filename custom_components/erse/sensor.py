"""
Component to track electricity tariff.

For more details about this component, please refer to the documentation
at http://github.com/dgomes/home-assistant-custom-components/electricity/
"""
import logging

from homeassistant.components.sensor import (
    ATTR_LAST_RESET,
    SensorDeviceClass,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.components.select.const import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
    ATTR_OPTION,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CURRENCY_EURO,
    EVENT_HOMEASSISTANT_START,
    ATTR_UNIT_OF_MEASUREMENT,
    ENERGY_WATT_HOUR,
    ENERGY_KILO_WATT_HOUR,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
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
    CONF_UTILITY_METERS,
    DOMAIN,
    ATTR_POWER_COST,
    ATTR_COST,
    ATTR_CURRENT_COST,
    ATTR_TARIFFS,
    ATTR_UTILITY_METERS,
)

_LOGGER = logging.getLogger(__name__)

ICON = "mdi:transmission-tower"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up an electricity monitor from a Config Entry."""

    entities = []

    if CONF_UTILITY_METERS in config_entry.data:
        entities.append(
            EletricityEntity(
                hass, config_entry.entry_id, config_entry.data[CONF_UTILITY_METERS]
            )
        )

    meter_entity = None
    for tariff in hass.data[DOMAIN][config_entry.entry_id].plano.tarifas:
        for meter_entity in config_entry.data[f"{tariff.name}{CONF_METER_SUFFIX}"]:
            entities.append(
                TariffCost(hass, config_entry.entry_id, tariff, meter_entity)
            )

    # TODO filter out to create a FixedCost of the monthly utility_meter entity
    entities.append(FixedCost(hass, config_entry.entry_id, meter_entity))

    async_add_entities(entities)


class TariffCost(SensorEntity):
    """Track cost of kWh for a given tariff"""

    def __init__(self, hass, entry_id, tariff, meter_entity):
        """Initialize cost tracker"""
        self.operator = hass.data[DOMAIN][entry_id]

        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = STATE_CLASS_TOTAL_INCREASING
        self._attr_native_unit_of_measurement = (
            CURRENCY_EURO 
        )

        self._attr_name = f"{meter_entity} cost"
        self._attr_unique_id = slugify(f"{entry_id} {meter_entity} cost")

        self._tariff = tariff
        self._meter_entity = meter_entity
        self._attr_should_poll = False

    @property
    def extra_state_attributes(self):
        attrs = {ATTR_COST: self.operator.plano.custo_tarifa(self._tariff)}
        return attrs

    async def async_added_to_hass(self):
        """Handle entity which will be tracked."""
        await super().async_added_to_hass()

        async def calc_costs(meter_state):

            if (
                meter_state
                and ATTR_UNIT_OF_MEASUREMENT in meter_state.attributes
                and meter_state.attributes[ATTR_UNIT_OF_MEASUREMENT]
                in [
                    ENERGY_WATT_HOUR,
                    ENERGY_KILO_WATT_HOUR,
                ]
            ):
                if meter_state.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
                    kwh = 0
                elif (
                    meter_state.attributes[ATTR_UNIT_OF_MEASUREMENT] == ENERGY_WATT_HOUR
                ):
                    kwh = float(meter_state.state) / 1000
                else:
                    kwh = float(meter_state.state)
            else:
                _LOGGER.error(
                    "Could not retrieve tariff sensor state or the sensor is not an energy sensor (wrong unit) from %s",
                    meter_state,
                )
                kwh = 0

            self._attr_native_value = round(
                self.operator.plano.custo_kWh_final(self._tariff, kwh), 2
            )
            _LOGGER.debug(
                "{%s} calc_costs(%s) = %s",
                self._attr_name,
                kwh,
                self._attr_native_value,
            )
            self.async_write_ha_state()

        @callback
        async def async_increment_cost(event):
            new_state = event.data.get("new_state")
            await calc_costs(new_state)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._meter_entity], async_increment_cost
            )
        )

        @callback
        async def initial_sync(_):
            meter_state = self.hass.states.get(self._meter_entity)
            self._attr_name = f"{meter_state.name} cost"
            await calc_costs(meter_state)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)


class FixedCost(SensorEntity):
    """Track fixed costs."""

    def __init__(self, hass, entry_id, any_meter) -> None:
        """Initialize fixed costs"""
        if any_meter is None:
            _LOGGER.error("No meter sensor entities defined")
            return

        self.operator = hass.data[DOMAIN][entry_id]

        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = STATE_CLASS_TOTAL_INCREASING
        self._attr_native_unit_of_measurement = (
            CURRENCY_EURO
        )

        self._attr_name = f"{self.operator} cost"
        self._attr_unique_id = slugify(f"{entry_id} {any_meter} fixed cost")

        self._meter = any_meter
        self._attr_should_poll = False

    async def async_added_to_hass(self):
        """Setups automations."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_track_time_change(
                self.hass, self.timer_update, hour=[0], minute=[0], second=[0]
            )
        )

        @callback
        async def initial_sync(_):
            await self.timer_update(dt_util.now())

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

    @callback
    async def timer_update(self, now):
        """Update fixed costs as days go by."""

        last_reset = self.hass.states.get(self._meter).attributes.get(ATTR_LAST_RESET)

        if last_reset:
            elapsed = now - dt_util.parse_datetime(last_reset)
        else:
            elapsed = now - now

        self._attr_native_value = round(
            self.operator.plano.custos_fixos(elapsed.days), 2
        )
        _LOGGER.debug("FixedCost = %s", self._attr_native_value)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        attrs = {ATTR_POWER_COST: round(self.operator.plano.custo_potencia(), 2)}
        return attrs


class EletricityEntity(Entity):
    """Representation of an Electricity Tariff tracker."""

    def __init__(self, hass, entry_id, utility_meters):
        """Initialize an Electricity Tariff Tracker."""
        self.operator = hass.data[DOMAIN][entry_id]
        self._attr_name = str(self.operator)
        self._utility_meters = utility_meters
        self._state = None
        self._attr_icon = ICON
        self._attr_unique_id = slugify(
            f"{entry_id} utility_meters {len(self._utility_meters)}"
        )
        self._attr_should_poll = False

    async def async_added_to_hass(self):
        """Setups all required entities and automations."""

        self.async_on_remove(
            async_track_time_change(
                self.hass, self.timer_update, minute=range(0, 60, 15)
            )
        )

        @callback
        async def initial_sync(_):
            await self.timer_update(dt_util.now())

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

    @callback
    async def timer_update(self, _):
        """Change tariff based on timer."""

        new_state = self.operator.plano.tarifa_actual().value

        if new_state != self._state:
            _LOGGER.debug("Changing from %s to %s", self._state, new_state)
            self._state = new_state

            await self.async_update_ha_state()

            for utility_meter in self._utility_meters:
                _LOGGER.debug("Change %s to %s", utility_meter, self._state)
                await self.hass.services.async_call(
                    SELECT_DOMAIN,
                    SERVICE_SELECT_OPTION,
                    {ATTR_ENTITY_ID: utility_meter, ATTR_OPTION: self._state},
                )

    @property
    def extra_state_attributes(self):
        attrs = {
            ATTR_CURRENT_COST: self.operator.plano.custo_tarifa(
                self.operator.plano.tarifa_actual()
            )
        }
        return attrs

    @property
    def state(self):
        """Return the state as the current tariff."""
        return self._state

    @property
    def capability_attributes(self):
        """Return capability attributes."""
        attr = {
            ATTR_TARIFFS: self.operator.plano.tarifas,
            ATTR_UTILITY_METERS: self._utility_meters,
        }
        return attr
