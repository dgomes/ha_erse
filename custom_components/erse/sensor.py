"""
Component to track electricity tariff.

For more details about this component, please refer to the documentation
at http://github.com/dgomes/home-assistant-custom-components/electricity/
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Final, Self
from dataclasses import dataclass
from homeassistant.helpers import issue_registry as ir

from homeassistant.components.select.const import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.select.const import DOMAIN as SELECT_DOMAIN
from homeassistant.components.sensor import ATTR_LAST_RESET, SensorEntity
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_START,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfEnergy
)
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    RestoreSensor,
    SensorDeviceClass,
    SensorExtraStoredData,
    SensorStateClass,
)

from .const import (
    ATTR_COST,
    ATTR_CURRENT_COST,
    ATTR_POWER_COST,
    ATTR_TARIFFS,
    ATTR_UTILITY_METERS,
    CONF_METER_SUFFIX,
    CONF_EXPORT_METER,
    CONF_UTILITY_METERS,
    COST_PRECISION,
    ENERGY_PRECISION,
    DOMAIN,
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

    if CONF_EXPORT_METER in config_entry.data:
        for tariff in hass.data[DOMAIN][config_entry.entry_id].plano.tarifas:
            entities.append(
                NetMeterSensor(
                    hass,
                    config_entry.entry_id,
                    config_entry.data[CONF_EXPORT_METER],
                    tariff,
                    [
                        meter_entity
                        for meter_entity in config_entry.data[
                            f"{tariff.name}{CONF_METER_SUFFIX}"
                        ]
                    ],
                )
            )

    # TODO filter out to create a FixedCost of the monthly utility_meter entity
    entities.append(FixedCost(hass, config_entry.entry_id, meter_entity))

    entities.append(TotalCost(hass, config_entry.entry_id, entities))

    async_add_entities(entities)


@dataclass
class NetMeterSensorExtraStoredData(SensorExtraStoredData):
    """Object to store extra NetMeterSensor data."""

    last_total: float | None
    last_export: float | None
    last_balance_datetime: datetime | None

    def as_dict(self) -> dict[str, Any]:
        """Return dictionary version of this object."""
        data = super().as_dict()
        data["last_total"] = self.last_total
        data["last_export"] = self.last_export
        if isinstance(self.last_balance_datetime, (datetime)):
            data["last_balance_datetime"] = self.last_balance_datetime.isoformat()
        return data

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        """Initialize a stored sensor state from a dict."""
        extra = SensorExtraStoredData.from_dict(restored)
        if extra is None:
            return None

        try:
            last_total = float(restored.get("last_total"))
        except (TypeError, ValueError):
            last_total = None

        try:
            last_export = float(restored.get("last_export"))
        except (TypeError, ValueError):
            last_export = None

        try:
            last_balance_datetime: datetime | None = dt_util.parse_datetime(
                restored.get("last_reset")
            )
        except (TypeError, ValueError):
            last_balance_datetime = None

        return cls(
            extra.native_value,
            extra.native_unit_of_measurement,
            last_total,
            last_export,
            last_balance_datetime,
        )


class TotalCost(ERSEMoneyEntity, SensorEntity):
    """Track total cost."""

    _attr_translation_key = "total_cost"

    def __init__(self, hass, entry_id, all_entities):
        """Initialize cost tracker"""
        super().__init__(hass.data[DOMAIN][entry_id])

        self._attr_unique_id = slugify(f"{entry_id} total cost")
        self._all_entities = all_entities

    async def async_added_to_hass(self):
        """Handle entity which will be tracked."""
        await super().async_added_to_hass()

        @callback
        async def calc_costs():
            try:
                self._attr_native_value = sum(
                    float(self.hass.states.get(cost).state)
                    for cost in self._all_entities
                )
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
            _LOGGER.debug("Total Cost is the sum of %s", self._all_entities)

            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self._all_entities, async_increment_cost
                )
            )

            await calc_costs()

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)


class NetMeterSensor(ERSEEntity, RestoreSensor):
    """Calculate Net Metering."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = ENERGY_PRECISION

    def __init__(self, hass, entry_id, export_entity, tariff, meter_entities):
        """Initialize netmeter tracker"""
        super().__init__(hass.data[DOMAIN][entry_id])

        self._attr_name = f"{tariff.value} Net"
        self._attr_unique_id = slugify(f"{entry_id} {tariff} netmeter")
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

        self._export_entity = export_entity
        self._tariff = tariff
        self._meter_entities = meter_entities
        self._last_total: float | None = None
        self._last_export: float | None = None
        self._attr_native_value: float = 0  # net metering
        self._last_balance_datetime: datetime | None = None

    async def async_added_to_hass(self):
        """Setups all required entities and automations."""

        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_sensor_data.native_value
            self._attr_native_unit_of_measurement = (
                last_sensor_data.native_unit_of_measurement
            )
            self._last_total = last_sensor_data.last_total
            self._last_export = last_sensor_data.last_export
            self._last_balance_datetime = last_sensor_data.last_balance_datetime

            _LOGGER.debug(
                "Restored state %s(%s) and last_total = %s, last_export = %s, last_balance_datetime = %s",
                self._attr_native_value,
                self._attr_native_unit_of_measurement,
                self._last_total,
                self._last_export,
                self._last_balance_datetime,
            )

        @callback
        async def sum_meters():
            """Sum all meters."""
            total = 0
            for meter in self._meter_entities:
                try:
                    total += float(self.hass.states.get(meter).state)
                except ValueError as err:
                    _LOGGER.error("Could not get state from %s: %s", meter, err)

            _LOGGER.debug(
                "%s sum_meters(%s) = %s",
                self._tariff.value,
                self._meter_entities,
                total,
            )
            return total

        @callback
        async def timer_update(_):
            """Change tariff based on timer."""
            self._last_balance_datetime = datetime.now()

            if (
                self._tariff
                != self._operator.plano.tarifa_actual(
                    datetime.now() - timedelta(minutes=1)
                ).value
            ):  # We need the tariff of the previous minute because it might have just changed
                self.async_write_ha_state()
                return  # tariff not active

            current_tariff = await sum_meters()
            period_total = current_tariff - self._last_total
            if period_total < 0:
                _LOGGER.debug(
                    "%s period_total < 0, probably a reset! using current value %s",
                    self.name,
                    current_tariff,
                )
                period_total = current_tariff
                self._last_total = current_tariff
            _LOGGER.debug("%s period_total = %s", self._tariff.value, period_total)

            current_export = float(self.hass.states.get(self._export_entity).state)
            period_export = current_export - self._last_export
            if period_export < 0:
                _LOGGER.debug(
                    "%s period_export < 0, probably a reset! using current value %s",
                    self.friendly_name,
                    current_export,
                )
                period_export = current_export
                self._last_export = current_export
            _LOGGER.debug("%s period_export = %s", self._tariff.value, period_export)

            # Did we consume from the network ?
            balance = period_total - period_export
            if balance > 0:
                self._attr_native_value += balance

            # update last values
            self._last_total = current_tariff
            self._last_export = current_export

            self.async_write_ha_state()

        @callback
        async def initial_sync(_):
            """Initialize netmeter counters."""

            if self._last_balance_datetime is None:
                self._last_balance_datetime = datetime.now()
                in_same_net_meter_period = False
            else:
                in_same_net_meter_period = (
                    datetime.now() - self._last_balance_datetime
                    <= timedelta(minutes=15)
                )

            if self._last_total is None or not in_same_net_meter_period:
                self._last_total = await sum_meters()
            if self._last_export is None or not in_same_net_meter_period:
                export_state = self.hass.states.get(self._export_entity)
                self._last_export = float(export_state.state)

                self._attr_native_unit_of_measurement = export_state.attributes.get(
                    ATTR_UNIT_OF_MEASUREMENT
                )

            """Validate that all meters have the same unit of measurement."""
            for meter in self._meter_entities:
                meter_state = self.hass.states.get(meter)
                meter_unit = meter_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                if self._attr_native_unit_of_measurement != meter_unit:
                    _LOGGER.error(
                        "Mismatching units of measurement for %s(%s) vs %s(%s)",
                        self._export_entity,
                        self._attr_native_unit_of_measurement,
                        meter,
                        meter_unit,
                    )
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        "unit_of_measurement_missmatch",
                        is_fixable=False,
                        is_persistent=True,
                        severity=ir.IssueSeverity.ERROR,
                        translation_key="unit_of_measurement_missmatch",
                        translation_placeholders={
                            "export_entity": self._export_entity,
                            "export_unit": self._attr_native_unit_of_measurement,
                            "meter_entity": meter,
                            "meter_unit": meter_unit,
                        },
                    )
                    return

            await timer_update(None)

            self.async_on_remove(
                async_track_time_change(
                    self.hass,
                    timer_update,
                    minute=range(0, 60, 15),
                    second=0,  # TODO after dev change 5 to 15
                )
            )

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

    @property
    def extra_restore_state_data(self) -> NetMeterSensorExtraStoredData:
        """Return sensor specific state data to be restored."""
        return NetMeterSensorExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            self._last_total,
            self._last_export,
            self._last_balance_datetime,
        )

    async def async_get_last_sensor_data(
        self,
    ) -> NetMeterSensorExtraStoredData | None:
        """Restore Net Meter Sensor Extra Stored Data."""
        if (restored_last_extra_data := await self.async_get_last_extra_data()) is None:
            return None

        return NetMeterSensorExtraStoredData.from_dict(
            restored_last_extra_data.as_dict()
        )


class TariffCost(ERSEMoneyEntity, SensorEntity):
    """Track cost of kWh for a given tariff"""

    def __init__(self, hass, entry_id, tariff, meter_entity):
        """Initialize cost tracker"""

        super().__init__(hass.data[DOMAIN][entry_id])

        self._attr_unique_id = slugify(f"{entry_id} {meter_entity} cost")

        self._tariff = tariff
        self._meter_entity = meter_entity

    @property
    def extra_state_attributes(self):
        return {ATTR_COST: self._operator.plano.custo_tarifa(self._tariff)}

    async def async_added_to_hass(self):
        """Handle entity which will be tracked."""
        await super().async_added_to_hass()

        @callback
        async def calc_costs(meter_state):
            if (
                meter_state
                and ATTR_UNIT_OF_MEASUREMENT in meter_state.attributes
                and meter_state.attributes[ATTR_UNIT_OF_MEASUREMENT]
                in [
                    UnitOfEnergy.WATT_HOUR,
                    UnitOfEnergy.KILO_WATT_HOUR,
                ]
            ):
                if meter_state.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
                    kwh = 0
                elif (
                    meter_state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.WATT_HOUR
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

            self._attr_native_value = self._operator.plano.custo_kWh_final(
                self._tariff, kwh
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
            self._attr_name = meter_state.attributes.get("friendly_name")
            await calc_costs(meter_state)

            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._meter_entity], async_increment_cost
                )
            )

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)


class FixedCost(ERSEMoneyEntity, SensorEntity):
    """Track fixed costs."""

    _attr_translation_key = "fixed_cost"

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

        self._attr_native_value = self._operator.plano.custos_fixos(elapsed.days)

        _LOGGER.debug("Fixed Cost = %s", self._attr_native_value)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {
            ATTR_POWER_COST: round(
                self._operator.plano.custo_potencia(), COST_PRECISION
            )
        }


class EletricityEntity(ERSEEntity):
    """Representation of an Electricity Tariff tracker."""

    _attr_translation_key = "tariff"

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

        @callback
        async def timer_update(_):
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

        @callback
        async def initial_sync(_):
            await timer_update(None)

            self.async_on_remove(
                async_track_time_change(
                    self.hass, timer_update, minute=range(0, 60, 15), second=0
                )
            )

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, initial_sync)

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
