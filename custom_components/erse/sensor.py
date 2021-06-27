"""
Component to track electricity tariff.

For more details about this component, please refer to the documentation
at http://github.com/dgomes/home-assistant-custom-components/electricity/
"""
import logging
from datetime import datetime, timedelta
from math import floor

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
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
from homeassistant.const import ATTR_ENTITY_ID, EVENT_HOMEASSISTANT_START
from homeassistant.core import callback, split_entity_id
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    CONF_COST_POTENCIA,
    CONF_OPERATOR,
    CONF_PLAN,
    CONF_UTILITY_METERS,
    COUNTRY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ATTR_TARIFFS = "tariffs"
ATTR_UTILITY_METERS = "utility meters"

ICON = "mdi:transmission-tower"

UTILITY_METER_NAME_FORMAT = "{} {}"

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up an electricity monitor from a Config Entry."""

    async_add_entities(
        [EletricityEntity(config_entry.title, config_entry.data)]
        + [
            EnergyCostSensor(utility_meter, config_entry.data)
            for utility_meter in config_entry.data[CONF_UTILITY_METERS]
        ]
    )


class EletricityEntity(Entity):
    """Representation of an Electricity Contract."""

    def __init__(self, name, config):
        """Initialize an Electricity Contract."""
        self._name = name
        self.operator = config[CONF_OPERATOR]
        self.plan = config[CONF_PLAN]
        self.utility_meters = config[CONF_UTILITY_METERS]
        self.my_plan = Operators[COUNTRY][self.operator](plan=self.plan)
        self._tariffs = self.my_plan.tariffs()
        self._state = None

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
    def name(self):
        """Return the name of the Electricity contract."""
        return self._name

    @property
    def state(self):
        """Return the state as the current tariff."""
        return self._state

    @property
    def unique_id(self):
        return slugify(
            str(self.operator) + str(self.plan) + str(len(self.utility_meters))
        )

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return ICON

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attr = dict()
        if self._tariffs:
            attr[ATTR_TARIFFS] = self._tariffs
        attr[ATTR_UTILITY_METERS] = [m for meter in self.utility_meters for m in meter]
        return attr


class EnergyCostSensor(SensorEntity):
    """Calculate costs incurred by consuming energy."""

    def __init__(self, utility_meter, config) -> None:
        """Initialize the sensor."""
        super().__init__()

        self.utility_meter = split_entity_id(utility_meter)[1]  # we only need the name

        self._attr_device_class = DEVICE_CLASS_MONETARY
        self._attr_name = utility_meter + " cost"
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_unit_of_measurement = "€"
        # self._attr_unique_id = config probably use config_entry_id

        self._tariffs = Operators[COUNTRY][config[CONF_OPERATOR]](
            plan=config[CONF_PLAN]
        ).tariffs()

        self._cost_potencia = config[CONF_COST_POTENCIA]
        self._cost_energia = {
            k: v
            for k, v in config.items()
            if k[5:]
            in [
                slugify(tariff) for tariff in self._tariffs
            ]  # filter config.items that contain cost_<tariff>
        }

    def _update_cost(self) -> None:
        """Update incurred costs."""

        last_reset = None
        cost_energia = 0

        for tariff in self._tariffs:
            energy_state = self.hass.states.get(
                f"sensor.{self.utility_meter}_{slugify(tariff)}"
            )

            if last_reset is None:
                last_reset = datetime.fromisoformat(
                    energy_state.attributes[ATTR_LAST_RESET]
                )

            energy_price = float(self._cost_energia[slugify(f"cost {tariff}")])

            energy = float(energy_state.state)

            cost_energia += energy * energy_price

        days = 1
        if last_reset:
            now = dt_util.utcnow()
            days += floor((now - last_reset) / timedelta(days=1))

        self._attr_state = round(self._cost_potencia * days + cost_energia, 2)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self._update_cost()

        @callback
        def async_state_changed_listener(*_) -> None:
            """Handle child updates."""
            self._update_cost()
            self.async_write_ha_state()

        entities = [
            f"sensor.{self.utility_meter}_{slugify(tariff)}" for tariff in self._tariffs
        ]

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, entities, async_state_changed_listener
            )
        )
