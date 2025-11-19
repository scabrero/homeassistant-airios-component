"""Binary sensor platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from pyairios.properties import AiriosDeviceProperty, AiriosVMDProperty

from .entity import (
    AiriosEntity,
    AiriosEntityDescription,
    find_matching_subentry,
)

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.constants import BatteryStatus, FaultStatus

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


def rf_comm_status_value_fn(v: int) -> bool | None:
    """Convert timedelta to sensor's value."""
    if v == 0:
        return True
    if v == 1:
        return False
    return None


def _battery_status_value_fn(v: BatteryStatus) -> bool | None:
    if v.available:
        return v.low != 0
    return None


def _fault_status_value_fn(v: FaultStatus) -> bool | None:
    if v.available:
        return v.fault
    return None


@dataclass(frozen=True, kw_only=True)
class AiriosBinarySensorEntityDescription(
    AiriosEntityDescription, BinarySensorEntityDescription
):
    """Airios binary sensor description."""

    value_fn: Callable[[Any], bool | None] | None = None


BINARY_SENSOR_ENTITIES: tuple[AiriosBinarySensorEntityDescription, ...] = (
    AiriosBinarySensorEntityDescription(
        ap=AiriosDeviceProperty.FAULT_STATUS,
        key=AiriosDeviceProperty.FAULT_STATUS.name.casefold(),
        translation_key="fault_status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_fault_status_value_fn,
    ),
    AiriosBinarySensorEntityDescription(
        ap=AiriosDeviceProperty.RF_COMM_STATUS,
        key=AiriosDeviceProperty.RF_COMM_STATUS.name.casefold(),
        translation_key="rf_comm_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=rf_comm_status_value_fn,
    ),
    AiriosBinarySensorEntityDescription(
        ap=AiriosVMDProperty.FILTER_DIRTY,
        key=AiriosVMDProperty.FILTER_DIRTY.name.casefold(),
        translation_key="filter_dirty",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    AiriosBinarySensorEntityDescription(
        ap=AiriosVMDProperty.DEFROST,
        key=AiriosVMDProperty.DEFROST.name.casefold(),
        translation_key="defrost",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    AiriosBinarySensorEntityDescription(
        ap=AiriosDeviceProperty.BATTERY_STATUS,
        key=AiriosDeviceProperty.BATTERY_STATUS.name.casefold(),
        translation_key="battery_status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_battery_status_value_fn,
    ),
    # VMD07-RP13 specific
    AiriosBinarySensorEntityDescription(
        ap=AiriosVMDProperty.BASIC_VENTILATION_ENABLE,
        key=AiriosVMDProperty.BASIC_VENTILATION_ENABLE.name.casefold(),
        translation_key="basic_vent_enable",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


class AiriosBinarySensorEntity(  # pyright: ignore[reportIncompatibleVariableOverride]
    AiriosEntity,
    BinarySensorEntity,
):
    """Airios binary sensor."""

    entity_description: AiriosBinarySensorEntityDescription

    def __init__(
        self,
        description: AiriosBinarySensorEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        modbus_address: int,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the binary sensor entity."""
        super().__init__(description.key, coordinator, modbus_address, subentry)
        self.entity_description = description  # type: ignore[override]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        try:
            result = self.fetch_result()
            if self.entity_description.value_fn:
                self._attr_is_on = self.entity_description.value_fn(result.value)
            else:
                self._attr_is_on = result.value
            self._attr_available = True
            if result.status is not None:
                self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError) as ex:
            _LOGGER.info(
                "Failed to update binary sensor entity for node=%s, property=%s: %s",
                f"0x{self.rf_address:06X}",
                self.entity_description.key,
                ex,
            )
            self._attr_is_on = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 # pylint: disable=unused-argument
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    for modbus_address, node in coordinator.data.nodes.items():
        subentry = find_matching_subentry(entry, modbus_address)
        entities: list[AiriosBinarySensorEntity] = [
            AiriosBinarySensorEntity(description, coordinator, modbus_address, subentry)
            for description in BINARY_SENSOR_ENTITIES
            if description.ap in node
        ]
        subentry_id = subentry.subentry_id if subentry else None
        async_add_entities(entities, config_subentry_id=subentry_id)
