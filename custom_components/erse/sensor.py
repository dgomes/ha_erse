"""
Component to track electricity tariff.

For more details about this component, please refer to the documentation
at http://github.com/dgomes/home-assistant-custom-components/electricity/
"""
import logging

from datetime import timedelta

from homeassistant.components.sensor import (
    ATTR_LAST_RESET,
    SensorEntity,
)
from homeassistant.components.select.const import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
    ATTR_OPTION,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
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

from homeassistant.helpers.device_registry import DeviceInfo


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

from .entity import ERSEEntity, ERSEMoneyEntity

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

    entities.append(TotalCost(hass, config_entry.entry_id, entities))

    async_add_entities(entities)


class TotalCost(ERSEMoneyEntity, SensorEntity):
    """Track total cost."""

    _attr_name = "Total cost"

    def __init__(self, hass, entry_id, all_entities):
        """Initialize cost tracker"""
        super().__init__(hass.data[DOMAIN][entry_id])

        self._attr_unique_id = slugify(f"{entry_id} total cost")
        self._all_entities = all_entities

    async def async_added_to_hass(self):
        """Handle entity which will be tracked."""
        await super().async_added_to_hass()

        async def calc_costs():
            try:
                total = sum(
                    float(self.hass.states.get(cost).state)
                    for cost in self._all_entities
                )

                self._attr_native_value = round(total, 2)
            except ValueError as err:
                _LOGGER.error(err)
                self._attr_native_value = None

            _LOGGER.debug("Total Cost = %s", self._attr_native_value)
            self.async_write_ha_state()

        @callback
        async def async_increment_cost(event):
            await calc_costs()

        @callback
        async def initial_sync(_):
            # convert objects into entity_ids
            self._all_entities = [
                entity.entity_id
                for entity in self._all_entities
                if isinstance(entity, (TariffCost, FixedCost))
            ]
            _LOGGER.debug("Total Cost = sum(%s)", self._all_entities)

            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self._all_entities, async_increment_cost
                )
            )

            await calc_costs()

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)


class TariffCost(ERSEMoneyEntity, SensorEntity):
    """Track cost of kWh for a given tariff"""

    def __init__(self, hass, entry_id, tariff, meter_entity):
        """Initialize cost tracker"""

        super().__init__(hass.data[DOMAIN][entry_id])

        meter_name = hass.states.get(meter_entity).attributes.get("friendly_name")

        self._attr_name = f"{meter_name} cost"
        self._attr_unique_id = slugify(f"{entry_id} {meter_entity} cost")

        self._tariff = tariff
        self._meter_entity = meter_entity

    @property
    def extra_state_attributes(self):
        return {ATTR_COST: self._operator.plano.custo_tarifa(self._tariff)}

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
                self._operator.plano.custo_kWh_final(self._tariff, kwh), 2
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

        @callback
        async def initial_sync(_):
            meter_state = self.hass.states.get(self._meter_entity)
            await calc_costs(meter_state)

            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._meter_entity], async_increment_cost
                )
            )

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)


class FixedCost(ERSEMoneyEntity, SensorEntity):
    """Track fixed costs."""

    _attr_name = "Fixed cost"

    def __init__(self, hass, entry_id, any_meter) -> None:
        """Initialize fixed costs"""
        if any_meter is None:
            _LOGGER.error("No meter sensor entities defined")
            return

        super().__init__(hass.data[DOMAIN][entry_id])

        self._attr_unique_id = slugify(f"{entry_id} {any_meter} fixed cost")

        self._meter = any_meter

    async def async_added_to_hass(self):
        """Setups automations."""
        await super().async_added_to_hass()

        @callback
        async def initial_sync(_):
            await self.timer_update(dt_util.now())

            self.async_on_remove(
                async_track_time_change(
                    self.hass, self.timer_update, hour=[0], minute=[0], second=[0]
                )
            )

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

    @callback
    async def timer_update(self, now):
        """Update fixed costs as days go by."""

        last_reset = self.hass.states.get(self._meter).attributes.get(ATTR_LAST_RESET)

        if last_reset:
            elapsed = now - dt_util.parse_datetime(last_reset)
        else:
            elapsed = timedelta(days=0)

        self._attr_native_value = round(
            self._operator.plano.custos_fixos(elapsed.days), 2
        )
        _LOGGER.debug("Fixed Cost = %s", self._attr_native_value)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {ATTR_POWER_COST: round(self._operator.plano.custo_potencia(), 2)}


class EletricityEntity(ERSEEntity):
    """Representation of an Electricity Tariff tracker."""

    _attr_name = "Tariff"

    def __init__(self, hass, entry_id, utility_meters):
        """Initialize an Electricity Tariff Tracker."""
        super().__init__(hass.data[DOMAIN][entry_id])
        self._utility_meters = utility_meters
        self._state = None
        self._attr_icon = ICON
        self._attr_unique_id = slugify(
            f"{entry_id} utility_meters {len(self._utility_meters)}"
        )

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

        new_state = self._operator.plano.tarifa_actual().value

        if new_state != self._state or self._state is None:
            _LOGGER.debug("Changing from %s to %s", self._state, new_state)
            self._state = new_state

            self.async_write_ha_state()

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
            ATTR_CURRENT_COST: self._operator.plano.custo_tarifa(
                self._operator.plano.tarifa_actual()
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
            ATTR_TARIFFS: self._operator.plano.tarifas,
            ATTR_UTILITY_METERS: self._utility_meters,
        }
        return attr
