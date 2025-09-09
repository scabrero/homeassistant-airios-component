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
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .entity import AiriosEntity

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.constants import BatteryStatus, FaultStatus
    from pyairios.data_model import AiriosNodeData

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
class AiriosBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Airios binary sensor description."""

    value_fn: Callable[[Any], bool | None] | None = None


class AiriosBinarySensorEntity(AiriosEntity, BinarySensorEntity):
    """Airios binary sensor."""

    entity_description: AiriosBinarySensorEntityDescription

    def __init__(
        self,
        description: AiriosBinarySensorEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        node: AiriosNodeData,
        via_config_entry: ConfigEntry | None,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the binary sensor entity."""
        super().__init__(description.key, coordinator, node, via_config_entry, subentry)
        self.entity_description = description

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        _LOGGER.debug(
            "Handle update for node %s binary sensor %s",
            f"{self.rf_address}",
            self.entity_description.key,
        )
        try:
            device = self.coordinator.data.nodes[self.modbus_address]
            result = device[self.entity_description.key]
            _LOGGER.debug(
                "Node %s, binary sensor %s, result %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                result,
            )
            if result is not None and result.value is not None:
                if self.entity_description.value_fn:
                    self._attr_is_on = self.entity_description.value_fn(result.value)
                else:
                    self._attr_is_on = result.value
                self._attr_available = self._attr_is_on is not None
                if result.status is not None:
                    self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError):
            _LOGGER.exception(
                "Failed to update binary node %s sensor %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
            )
            self._attr_is_on = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()


NODE_BINARY_SENSOR_ENTITIES: tuple[AiriosBinarySensorEntityDescription, ...] = (
    AiriosBinarySensorEntityDescription(
        key="fault_status",
        translation_key="fault_status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_fault_status_value_fn,
    ),
    AiriosBinarySensorEntityDescription(
        key="rf_comm_status",
        translation_key="rf_comm_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=rf_comm_status_value_fn,
    ),
)

# These tuples must match the NodeData defined in pyairios models/
# When a new device VMD-02xxx is added that doesn't support the following binary sensors,
# or in fact supports more than these: rename or subclass

VMD_02_BINARY_SENSOR_ENTITIES: tuple[AiriosBinarySensorEntityDescription, ...] = (
    AiriosBinarySensorEntityDescription(
        key="filter_dirty",
        translation_key="filter_dirty",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    AiriosBinarySensorEntityDescription(
        key="defrost",
        translation_key="defrost",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)

VMD_07_BINARY_SENSOR_ENTITIES: tuple[AiriosBinarySensorEntityDescription, ...] = (
    AiriosBinarySensorEntityDescription(
        key="filter_dirty",
        translation_key="filter_dirty",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    AiriosBinarySensorEntityDescription(
        key="basic_ventilation_enable",
        translation_key="base_vent_enabled",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)

VMN_BINARY_SENSOR_ENTITIES: tuple[AiriosBinarySensorEntityDescription, ...] = (
    AiriosBinarySensorEntityDescription(
        key="battery_status",
        translation_key="battery_status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_battery_status_value_fn,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    # fetch model definitions from bridge data
    bridge_id = entry.data[CONF_ADDRESS]
    prids = coordinator.data.nodes[bridge_id]["product_ids"]

    for modbus_address, node in coordinator.data.nodes.items():
        # Find matching subentry
        subentry_id = None
        subentry = None
        via_config_entry = None
        for se_id, se in entry.subentries.items():
            if se.data[CONF_ADDRESS] == modbus_address:
                subentry_id = se_id
                subentry = se
                via_config_entry = entry

        entities: list[AiriosBinarySensorEntity] = [
            AiriosBinarySensorEntity(
                description,
                coordinator,
                node,
                via_config_entry,
                subentry,
            )
            for description in NODE_BINARY_SENSOR_ENTITIES
        ]
        product_id = node["product_id"]
        if product_id is None:
            msg = "Failed to fetch product id from node"
            raise ConfigEntryNotReady(msg)

        for key, _id in prids.items():
            # dict of ids by model_key (names). Can we use node["product_name"] as key?
            _LOGGER.debug(
                f"Binary Sensor setup - checking node {product_id} against prid {key}, {_id}"
            )
            if product_id == _id:
                if key.startswith(
                    "VMD-02"
                ):  # only controllers, add is_controller() in pyairios?
                    entities.extend(
                        [
                            AiriosBinarySensorEntity(
                                description,
                                coordinator,
                                node,
                                via_config_entry,
                                subentry,
                            )
                            for description in VMD_02_BINARY_SENSOR_ENTITIES
                        ]
                    )
                elif key.startswith(
                    "VMD-07"
                ):  # only controllers, add is_controller() in pyairios?
                    entities.extend(
                        [
                            AiriosBinarySensorEntity(
                                description,
                                coordinator,
                                node,
                                via_config_entry,
                                subentry,
                            )
                            for description in VMD_07_BINARY_SENSOR_ENTITIES
                            # TODO first check if model supports this: if binary_sensor coordinator.api().etc...
                        ]
                    )
                elif key.startswith("VMN-"):
                    entities.extend(
                        [
                            AiriosBinarySensorEntity(
                                description,
                                coordinator,
                                node,
                                via_config_entry,
                                subentry,
                            )
                            for description in VMN_BINARY_SENSOR_ENTITIES
                        ]
                    )
                else:
                    _LOGGER.debug(f"Skipping binary_sensor setup for node {key}")
        async_add_entities(entities, config_subentry_id=subentry_id)
