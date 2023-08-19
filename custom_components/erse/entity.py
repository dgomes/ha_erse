"""Support for ERSE entities."""
from __future__ import annotations

from homeassistant.components.sensor import STATE_CLASS_TOTAL, SensorDeviceClass
from homeassistant.const import CURRENCY_EURO
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from pyerse.comercializador import Comercializador

from .const import COST_PRECISION, DOMAIN


class ERSEEntity(Entity):
    """Defines a base ERSE entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        operator: Comercializador,
    ) -> None:
        """Init the ERSE base entity."""
        super().__init__()
        self._operator = operator

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._operator))},
            name=f"{self._operator}",
            manufacturer="ERSE",
            model="Cost Tracker",
        )


class ERSEMoneyEntity(ERSEEntity):
    """Defines a monetary ERSE entity."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = STATE_CLASS_TOTAL
    _attr_native_unit_of_measurement = CURRENCY_EURO
    _attr_suggested_display_precision = COST_PRECISION
