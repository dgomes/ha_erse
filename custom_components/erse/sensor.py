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
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
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

    async_add_entities([EletricityEntity(config_entry.title, config_entry.data)])


class EletricityEntity(Entity):
    """Representation of an Electricity Contract."""

    def __init__(self, name, config):
        """Initialize an Electricity Contract."""
        self._name = name
        self.operator = config[CONF_OPERATOR]
        self.plan = config[CONF_PLAN]
        self.utility_meters = config[CONF_UTILITY_METER]
        self.my_plan = Operators[COUNTRY][self.operator](plan=self.plan)
        self._tariffs = self.my_plan.tariffs()
        self._state = None

    async def async_added_to_hass(self):
        """Setups all required entities and automations."""
        self._state = self.my_plan.current_tariff(dt_util.now())
        async_track_time_change(self.hass, self.timer_update, minute=range(0, 60, 15))

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
        attr[ATTR_UTILITY_METERS] = self.utility_meters
        return attr
