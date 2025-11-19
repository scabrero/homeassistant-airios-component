"""Sensor platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from pyairios.constants import (
    VMDBypassPosition,
    VMDCO2Level,
    VMDErrorCode,
    VMDHeater,
    VMDHeaterStatus,
    VMDSensorStatus,
    VMDTemperature,
)
from pyairios.properties import (
    AiriosBridgeProperty,
    AiriosVMDProperty,
)

from .entity import (
    AiriosEntity,
    AiriosEntityDescription,
    find_matching_subentry,
)

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import timedelta

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AiriosSensorEntityDescription(AiriosEntityDescription, SensorEntityDescription):
    """Airios sensor description."""

    value_fn: Callable[[Any], StateType] | None = None


VMD_ERROR_CODE_MAP: dict[VMDErrorCode, str] = {
    VMDErrorCode.NO_ERROR: "no_error",
    VMDErrorCode.NON_SPECIFIC_FAULT: "non_specific_fault",
    VMDErrorCode.EMERGENCY_STOP: "emergency_stop",
    VMDErrorCode.FAN_1_ERROR: "fan_1_error",
    VMDErrorCode.FAN_2_ERROR: "fan_2_error",
    VMDErrorCode.X20_SENSOR_ERROR: "x20_sensor_error",
    VMDErrorCode.X21_SENSOR_ERROR: "x21_sensor_error",
    VMDErrorCode.X22_SENSOR_ERROR: "x22_sensor_error",
    VMDErrorCode.X23_SENSOR_ERROR: "x23_sensor_error",
    VMDErrorCode.BINDING_MODE_ACTIVE: "binding_mode_active",
    VMDErrorCode.IDENTIFICATION_ACTIVE: "identification_active",
}


def power_on_time_value_fn(v: timedelta) -> StateType:
    """Convert timedelta to sensor's value."""
    return v.total_seconds()


def error_code_value_fn(v: VMDErrorCode) -> StateType:
    """Convert VMDErrorCode to sensor's value."""
    return VMD_ERROR_CODE_MAP.get(v)


def temperature_value_fn(v: VMDTemperature) -> StateType:
    """Convert VMDTemperature to sensor's value."""
    if v.status == VMDSensorStatus.OK:
        return v.temperature
    return None


def bypass_position_value_fn(v: VMDBypassPosition) -> StateType:
    """Convert VMDTemperature to sensor's value."""
    if not v.error:
        return v.position
    return None


def co2_value_fn(v: VMDCO2Level) -> StateType:
    """Convert VMDCO2Level to sensor's value."""
    if v.status == VMDSensorStatus.OK:
        return v.co2
    return None


def override_remaining_time_value_fn(v: int) -> StateType:
    """Entity return not available when 0."""
    if v == 0:
        return None
    return v


def postheater_value_fn(v: VMDHeater) -> StateType:
    """Convert VMDHeater to sensor's value."""
    if v.status == VMDHeaterStatus.OK:
        return v.level
    return None


SENSOR_ENTITIES: tuple[AiriosSensorEntityDescription, ...] = (
    AiriosSensorEntityDescription(
        ap=AiriosBridgeProperty.RF_LOAD_LAST_HOUR,
        key=AiriosBridgeProperty.RF_LOAD_LAST_HOUR.name.casefold(),
        translation_key="rf_load_last_hour",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosBridgeProperty.RF_LOAD_CURRENT_HOUR,
        key=AiriosBridgeProperty.RF_LOAD_CURRENT_HOUR.name.casefold(),
        translation_key="rf_load_current_hour",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosBridgeProperty.MESSAGES_SEND_LAST_HOUR,
        key=AiriosBridgeProperty.MESSAGES_SEND_LAST_HOUR.name.casefold(),
        translation_key="rf_sent_messages_last_hour",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosBridgeProperty.MESSAGES_SEND_CURRENT_HOUR,
        key=AiriosBridgeProperty.MESSAGES_SEND_CURRENT_HOUR.name.casefold(),
        translation_key="rf_sent_messages_current_hour",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosBridgeProperty.UPTIME,
        key=AiriosBridgeProperty.UPTIME.name.casefold(),
        translation_key="power_on_time",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.TEMPERATURE_EXHAUST,
        key=AiriosVMDProperty.TEMPERATURE_EXHAUST.name.casefold(),
        translation_key="indoor_air_temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=temperature_value_fn,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.TEMPERATURE_INLET,
        key=AiriosVMDProperty.TEMPERATURE_INLET.name.casefold(),
        translation_key="outdoor_air_temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=temperature_value_fn,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.TEMPERATURE_OUTLET,
        key=AiriosVMDProperty.TEMPERATURE_OUTLET.name.casefold(),
        translation_key="exhaust_air_temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=temperature_value_fn,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.TEMPERATURE_SUPPLY,
        key=AiriosVMDProperty.TEMPERATURE_SUPPLY.name.casefold(),
        translation_key="supply_air_temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=temperature_value_fn,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.FAN_RPM_EXHAUST,
        key=AiriosVMDProperty.FAN_RPM_EXHAUST.name.casefold(),
        translation_key="exhaust_fan_rpm",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.FAN_RPM_SUPPLY,
        key=AiriosVMDProperty.FAN_RPM_SUPPLY.name.casefold(),
        translation_key="supply_fan_rpm",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.FAN_SPEED_SUPPLY,
        key=AiriosVMDProperty.FAN_SPEED_SUPPLY.name.casefold(),
        translation_key="supply_fan_speed",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.FAN_SPEED_EXHAUST,
        key=AiriosVMDProperty.FAN_SPEED_EXHAUST.name.casefold(),
        translation_key="exhaust_fan_speed",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.ERROR_CODE,
        key=AiriosVMDProperty.ERROR_CODE.name.casefold(),
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=list(dict.fromkeys(VMD_ERROR_CODE_MAP.values())),
        value_fn=error_code_value_fn,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.FILTER_DURATION,
        key=AiriosVMDProperty.FILTER_DURATION.name.casefold(),
        translation_key="filter_duration_days",
        native_unit_of_measurement=UnitOfTime.DAYS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.FILTER_REMAINING_PERCENT,
        key=AiriosVMDProperty.FILTER_REMAINING_PERCENT.name.casefold(),
        translation_key="filter_remaining_percent",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.BYPASS_POSITION,
        key=AiriosVMDProperty.BYPASS_POSITION.name.casefold(),
        translation_key="bypass_position",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=bypass_position_value_fn,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.POSTHEATER,
        key=AiriosVMDProperty.POSTHEATER.name.casefold(),
        translation_key="postheater",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=postheater_value_fn,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.VENTILATION_SPEED_OVERRIDE_REMAINING_TIME,
        key=AiriosVMDProperty.VENTILATION_SPEED_OVERRIDE_REMAINING_TIME.name.casefold(),
        translation_key="override_remaining_time",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=override_remaining_time_value_fn,
    ),
    # VMD07-RP13 specific
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.CO2_LEVEL,
        key=AiriosVMDProperty.CO2_LEVEL.name.casefold(),
        translation_key="co2_level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        value_fn=co2_value_fn,
    ),
    AiriosSensorEntityDescription(
        ap=AiriosVMDProperty.CO2_CONTROL_SETPOINT,
        key=AiriosVMDProperty.CO2_CONTROL_SETPOINT.name.casefold(),
        translation_key="co2_setpoint",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


class AiriosSensorEntity(  # pyright: ignore[reportIncompatibleVariableOverride]
    AiriosEntity,
    SensorEntity,
):
    """Airios sensor."""

    entity_description: AiriosSensorEntityDescription

    def __init__(
        self,
        description: AiriosSensorEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        modbus_address: int,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the Airios sensor entity."""
        super().__init__(description.key, coordinator, modbus_address, subentry)
        self.entity_description = description  # type: ignore[override]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        try:
            result = self.fetch_result()
            if self.entity_description.value_fn:
                self._attr_native_value = self.entity_description.value_fn(result.value)
            else:
                self._attr_native_value = result.value
            self._attr_available = self._attr_native_value is not None
            if result.status is not None:
                self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError) as ex:
            _LOGGER.info(
                "Failed to update sensor entity for node=%s, property=%s: %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                ex,
            )
            self._attr_native_value = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 # pylint: disable=unused-argument
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    for modbus_address, node in coordinator.data.nodes.items():
        subentry = find_matching_subentry(entry, modbus_address)
        entities: list[AiriosSensorEntity] = [
            AiriosSensorEntity(description, coordinator, modbus_address, subentry)
            for description in SENSOR_ENTITIES
            if description.ap in node
        ]
        subentry_id = subentry.subentry_id if subentry else None
        async_add_entities(entities, config_subentry_id=subentry_id)
