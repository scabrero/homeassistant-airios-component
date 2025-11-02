"""Fan platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import Any, final

from homeassistant.components.fan import (
    FanEntity,
    FanEntityDescription,
    FanEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from pyairios.constants import (
    VMDCapabilities,
    VMDRequestedVentilationSpeed,
    VMDVentilationSpeed,
)
from pyairios.exceptions import AiriosException
from pyairios.properties import (
    AiriosDeviceProperty,
    AiriosVMDProperty,
)

from .entity import (
    AiriosEntity,
    AiriosEntityDescription,
    find_matching_subentry,
)
from .services import (
    SERVICE_FILTER_RESET,
    SERVICE_SCHEMA_SET_PRESET_FAN_SPEED,
    SERVICE_SCHEMA_SET_PRESET_MODE_DURATION,
    SERVICE_SET_PRESET_FAN_SPEED_AWAY,
    SERVICE_SET_PRESET_FAN_SPEED_HIGH,
    SERVICE_SET_PRESET_FAN_SPEED_LOW,
    SERVICE_SET_PRESET_FAN_SPEED_MEDIUM,
    SERVICE_SET_PRESET_MODE_DURATION,
)

if typing.TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import AiriosConfigEntry
    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

PRESET_NAMES = {
    VMDVentilationSpeed.OFF: "off",
    VMDVentilationSpeed.LOW: "low",
    VMDVentilationSpeed.MID: "medium",
    VMDVentilationSpeed.HIGH: "high",
    VMDVentilationSpeed.OVERRIDE_LOW: "low_override",
    VMDVentilationSpeed.OVERRIDE_MID: "medium_override",
    VMDVentilationSpeed.OVERRIDE_HIGH: "high_override",
    VMDVentilationSpeed.AWAY: "away",
    VMDVentilationSpeed.BOOST: "boost",
    VMDVentilationSpeed.AUTO: "auto",
}

PRESET_VALUES = {value: key for (key, value) in PRESET_NAMES.items()}

PRESET_TO_VMD_SPEED = {
    "off": VMDRequestedVentilationSpeed.OFF,
    "low": VMDRequestedVentilationSpeed.LOW,
    "medium": VMDRequestedVentilationSpeed.MID,
    "high": VMDRequestedVentilationSpeed.HIGH,
    "low_override": VMDRequestedVentilationSpeed.LOW,
    "medium_override": VMDRequestedVentilationSpeed.MID,
    "high_override": VMDRequestedVentilationSpeed.HIGH,
    "away": VMDRequestedVentilationSpeed.AWAY,
    "boost": VMDRequestedVentilationSpeed.BOOST,
    "auto": VMDRequestedVentilationSpeed.AUTO,
}


@dataclass(frozen=True, kw_only=True)
class AiriosFanEntityDescription(AiriosEntityDescription, FanEntityDescription):
    """Airios fan description."""


FAN_ENTITIES: tuple[AiriosFanEntityDescription, ...] = (
    AiriosFanEntityDescription(
        ap=AiriosVMDProperty.CURRENT_VENTILATION_SPEED,
        key=AiriosVMDProperty.CURRENT_VENTILATION_SPEED.name.casefold(),
        translation_key="ventilation_speed",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 # pylint: disable=unused-argument
    entry: AiriosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    for modbus_address, node in coordinator.data.nodes.items():
        capabilities = None
        if AiriosVMDProperty.CAPABILITIES in node:
            capabilities = node[AiriosVMDProperty.CAPABILITIES].value

        subentry = find_matching_subentry(entry, modbus_address)
        entities: list[AiriosFanEntity] = [
            AiriosFanEntity(
                description, coordinator, capabilities, modbus_address, subentry
            )
            for description in FAN_ENTITIES
            if description.ap in node
        ]
        subentry_id = subentry.subentry_id if subentry else None
        async_add_entities(entities, config_subentry_id=subentry_id)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_PRESET_FAN_SPEED_AWAY,
        SERVICE_SCHEMA_SET_PRESET_FAN_SPEED,
        "async_set_preset_fan_speed_away",
    )
    platform.async_register_entity_service(
        SERVICE_SET_PRESET_FAN_SPEED_LOW,
        SERVICE_SCHEMA_SET_PRESET_FAN_SPEED,
        "async_set_preset_fan_speed_low",
    )
    platform.async_register_entity_service(
        SERVICE_SET_PRESET_FAN_SPEED_MEDIUM,
        SERVICE_SCHEMA_SET_PRESET_FAN_SPEED,
        "async_set_preset_fan_speed_low",
    )
    platform.async_register_entity_service(
        SERVICE_SET_PRESET_FAN_SPEED_HIGH,
        SERVICE_SCHEMA_SET_PRESET_FAN_SPEED,
        "async_set_preset_fan_speed_low",
    )
    platform.async_register_entity_service(
        SERVICE_SET_PRESET_MODE_DURATION,
        SERVICE_SCHEMA_SET_PRESET_MODE_DURATION,
        "async_set_preset_mode_duration",
    )
    platform.async_register_entity_service(
        SERVICE_FILTER_RESET,
        None,
        "async_filter_reset",
    )


class AiriosFanEntity(  # pyright: ignore[reportIncompatibleVariableOverride]
    AiriosEntity,
    FanEntity,
):
    """Airios fan entity."""

    _attr_name = None
    _attr_supported_features = FanEntityFeature.PRESET_MODE
    entity_description: AiriosFanEntityDescription

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        description: AiriosFanEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        capabilities: VMDCapabilities | None,
        modbus_address: int,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the Airios fan entity."""
        super().__init__(description.key, coordinator, modbus_address, subentry)
        self.entity_description = description  # type: ignore[override]

        data = coordinator.data.nodes[self.modbus_address]
        _LOGGER.info(
            "Fan for node %s@%s capable of %s",
            data[AiriosDeviceProperty.PRODUCT_NAME],
            self.modbus_address,
            capabilities,
        )

        self._attr_preset_modes = [
            PRESET_NAMES[VMDVentilationSpeed.LOW],
            PRESET_NAMES[VMDVentilationSpeed.MID],
            PRESET_NAMES[VMDVentilationSpeed.HIGH],
        ]

        if capabilities:
            if VMDCapabilities.OFF_CAPABLE in capabilities:
                self._attr_supported_features |= FanEntityFeature.TURN_OFF
                self._attr_supported_features |= FanEntityFeature.TURN_ON
                self._attr_preset_modes.append(PRESET_NAMES[VMDVentilationSpeed.OFF])

            if VMDCapabilities.AUTO_MODE_CAPABLE in capabilities:
                self._attr_preset_modes.append(PRESET_NAMES[VMDVentilationSpeed.AUTO])
            if VMDCapabilities.AWAY_MODE_CAPABLE in capabilities:
                self._attr_preset_modes.append(PRESET_NAMES[VMDVentilationSpeed.AWAY])
            if VMDCapabilities.BOOST_MODE_CAPABLE in capabilities:
                self._attr_preset_modes.append(PRESET_NAMES[VMDVentilationSpeed.BOOST])
            if VMDCapabilities.TIMER_CAPABLE in capabilities:
                self._attr_preset_modes.append(
                    PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_LOW]
                )
                self._attr_preset_modes.append(
                    PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_MID]
                )
                self._attr_preset_modes.append(
                    PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_HIGH]
                )

    async def _turn_on_internal(
        self,
        percentage: int | None = None,  # noqa: ARG002 # pylint: disable=unused-argument
        preset_mode: str | None = None,
    ) -> bool:
        if self.is_on:
            return False
        if preset_mode is None:
            preset_mode = PRESET_NAMES[VMDVentilationSpeed.MID]
        return await self._set_preset_mode_internal(preset_mode)

    async def _turn_off_internal(self) -> bool:
        if not self.is_on:
            return False
        return await self._set_preset_mode_internal(
            PRESET_NAMES[VMDVentilationSpeed.OFF]
        )

    async def _set_preset_mode_internal(self, preset_mode: str) -> bool:
        if preset_mode == self.preset_mode:
            return False

        try:
            dev = await self.api().node(self.modbus_address)
            vmd_speed = PRESET_TO_VMD_SPEED[preset_mode]

            # Handle temporary overrides
            if preset_mode == PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_LOW]:
                return await dev.set(AiriosVMDProperty.OVERRIDE_TIME_SPEED_LOW, 60)

            if preset_mode == PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_MID]:
                return await dev.set(AiriosVMDProperty.OVERRIDE_TIME_SPEED_MID, 60)

            if preset_mode == PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_HIGH]:
                return await dev.set(AiriosVMDProperty.OVERRIDE_TIME_SPEED_HIGH, 60)

            return await dev.set(
                AiriosVMDProperty.REQUESTED_VENTILATION_SPEED, vmd_speed
            )
        except AiriosException as ex:
            msg = f"Failed to set preset {preset_mode}"
            raise HomeAssistantError(msg) from ex

    @property
    def is_on(self) -> bool | None:
        """Return true if the entity is on."""
        return (
            self.preset_mode is not None
            and self.preset_mode != PRESET_NAMES[VMDVentilationSpeed.OFF]
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,  # noqa: ARG002 # pylint: disable=unused-argument
    ) -> None:
        """Turn on the fan."""
        update_needed = await self._turn_on_internal(percentage, preset_mode)
        if update_needed:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002 # pylint: disable=unused-argument
        """Turn off the fan."""
        update_needed = await self._turn_off_internal()
        if update_needed:
            await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        update_needed = await self._set_preset_mode_internal(preset_mode)
        if update_needed:
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        try:
            result = self.fetch_result()
            self._attr_preset_mode = PRESET_NAMES[result.value]
            self._attr_available = self._attr_preset_mode is not None
            if result is not None and result.status is not None:
                self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError) as ex:
            _LOGGER.info(
                "Failed to update fan entity for node=%s, property=%s: %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                ex,
            )
            self._attr_available = False
        finally:
            if self._attr_available:
                self._unavailable_logged = False
            elif not self._unavailable_logged:
                _LOGGER.info(
                    "Node %s fan %s is unavailable",
                    f"0x{self.rf_address:08X}",
                    self.entity_description.key,
                )
                self._unavailable_logged = True
            self.async_write_ha_state()

    @final
    async def async_set_preset_fan_speed_away(
        self,
        supply_fan_speed: int,
        exhaust_fan_speed: int,
    ) -> bool:
        """Set the fans speeds for the away preset mode."""
        dev = await self.api().node(self.modbus_address)
        data = self.coordinator.data.nodes[self.modbus_address]
        if (
            AiriosVMDProperty.FAN_SPEED_AWAY_SUPPLY,
            AiriosVMDProperty.FAN_SPEED_AWAY_EXHAUST,
        ) not in data:
            msg = f"Property not supported by device {dev!s}."
            raise HomeAssistantError(msg)
        msg = (
            "Setting fans speeds for away preset on node "
            f"{dev} to: supply={supply_fan_speed}%%, exhaust={exhaust_fan_speed}%%"
        )
        _LOGGER.info(msg)
        try:
            if not await dev.set(
                AiriosVMDProperty.FAN_SPEED_AWAY_SUPPLY, supply_fan_speed
            ):
                msg = f"Failed to set supply fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
            if not await dev.set(
                AiriosVMDProperty.FAN_SPEED_AWAY_EXHAUST, exhaust_fan_speed
            ):
                msg = f"Failed to set exhaust fan speed to {exhaust_fan_speed}"
                raise HomeAssistantError(msg)
        except AiriosException as ex:
            msg = f"Failed to set fan speeds: {ex}"
            raise HomeAssistantError(msg) from ex
        return True

    @final
    async def async_set_preset_fan_speed_low(
        self,
        supply_fan_speed: int,
        exhaust_fan_speed: int,
    ) -> bool:
        """Set the fans speeds for the low preset mode."""
        dev = await self.api().node(self.modbus_address)
        data = self.coordinator.data.nodes[self.modbus_address]
        if (
            AiriosVMDProperty.FAN_SPEED_LOW_SUPPLY,
            AiriosVMDProperty.FAN_SPEED_LOW_EXHAUST,
        ) not in data:
            msg = f"Property not supported by device {dev!s}."
            raise HomeAssistantError(msg)
        infomsg = (
            "Setting fans speeds for low preset on node "
            f"{dev} to: supply={supply_fan_speed}%%, exhaust={exhaust_fan_speed}%%",
        )
        _LOGGER.info(infomsg)
        try:
            if not await dev.set(
                AiriosVMDProperty.FAN_SPEED_LOW_SUPPLY, supply_fan_speed
            ):
                msg = f"Failed to set supply fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
            if not await dev.set(
                AiriosVMDProperty.FAN_SPEED_LOW_EXHAUST, exhaust_fan_speed
            ):
                msg = f"Failed to set exhaust fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
        except AiriosException as ex:
            msg = f"Failed to set fan speeds: {ex}"
            raise HomeAssistantError(msg) from ex
        return True

    @final
    async def async_set_preset_fan_speed_medium(
        self,
        supply_fan_speed: int,
        exhaust_fan_speed: int,
    ) -> bool:
        """Set the fans speeds for the medium preset mode."""
        dev = await self.api().node(self.modbus_address)
        data = self.coordinator.data.nodes[self.modbus_address]
        if (
            AiriosVMDProperty.FAN_SPEED_MID_SUPPLY,
            AiriosVMDProperty.FAN_SPEED_MID_EXHAUST,
        ) not in data:
            msg = f"Property not supported by device {dev!s}."
            raise HomeAssistantError(msg)
        infomsg = (
            "Setting fans speeds for medium preset on node "
            f"{dev} to: supply={supply_fan_speed}%%, exhaust={exhaust_fan_speed}%%",
        )
        _LOGGER.info(infomsg)
        try:
            if not await dev.set(
                AiriosVMDProperty.FAN_SPEED_MID_SUPPLY, supply_fan_speed
            ):
                msg = f"Failed to set supply fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
            if not await dev.set(
                AiriosVMDProperty.FAN_SPEED_MID_EXHAUST, exhaust_fan_speed
            ):
                msg = f"Failed to set exhaust fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
        except AiriosException as ex:
            msg = f"Failed to set fan speeds: {ex}"
            raise HomeAssistantError(msg) from ex
        return True

    @final
    async def async_set_preset_fan_speed_high(
        self,
        supply_fan_speed: int,
        exhaust_fan_speed: int,
    ) -> bool:
        """Set the fans speeds for the high preset mode."""
        dev = await self.api().node(self.modbus_address)
        data = self.coordinator.data.nodes[self.modbus_address]
        if (
            AiriosVMDProperty.FAN_SPEED_HIGH_SUPPLY,
            AiriosVMDProperty.FAN_SPEED_HIGH_EXHAUST,
        ) not in data:
            msg = f"Property not supported by device {dev!s}."
            raise HomeAssistantError(msg)

        infomsg = (
            "Setting fans speeds for high preset on node "
            f"{dev} to: supply={supply_fan_speed}%%, exhaust={exhaust_fan_speed}%%",
        )
        _LOGGER.info(infomsg)
        try:
            dev = await self.api().node(self.modbus_address)
            if not await dev.set(
                AiriosVMDProperty.FAN_SPEED_HIGH_SUPPLY, supply_fan_speed
            ):
                msg = f"Failed to set supply fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
            if not await dev.set(
                AiriosVMDProperty.FAN_SPEED_HIGH_EXHAUST, exhaust_fan_speed
            ):
                msg = f"Failed to set exhaust fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
        except AiriosException as ex:
            msg = f"Failed to set fan speeds: {ex}"
            raise HomeAssistantError(msg) from ex
        return True

    @final
    async def async_set_preset_mode_duration(
        self, preset_mode: str, preset_override_time: int
    ) -> bool:
        """Set the preset mode for a limited time."""
        dev = await self.api().node(self.modbus_address)
        data = self.coordinator.data.nodes[self.modbus_address]
        if (
            AiriosVMDProperty.REQUESTED_VENTILATION_SPEED,
            AiriosVMDProperty.CAPABILITIES,
        ) not in data:
            msg = f"Property not supported by device {dev!s}."
            raise HomeAssistantError(msg)

        caps = data[AiriosVMDProperty.CAPABILITIES].value
        if VMDCapabilities.TIMER_CAPABLE not in caps:
            msg = f"Device {dev!s} does not support preset temporary override"
            raise HomeAssistantError(msg)

        vmd_speed = PRESET_TO_VMD_SPEED[preset_mode]
        _LOGGER.info(
            "Setting preset mode on node %s to: %s for %s minutes",
            str(dev),
            vmd_speed,
            preset_override_time,
        )
        try:
            if preset_mode == PRESET_NAMES[VMDVentilationSpeed.LOW]:
                return await dev.set(
                    AiriosVMDProperty.OVERRIDE_TIME_SPEED_LOW, preset_override_time
                )
            if preset_mode == PRESET_NAMES[VMDVentilationSpeed.MID]:
                return await dev.set(
                    AiriosVMDProperty.OVERRIDE_TIME_SPEED_MID, preset_override_time
                )
            if preset_mode == PRESET_NAMES[VMDVentilationSpeed.HIGH]:
                return await dev.set(
                    AiriosVMDProperty.OVERRIDE_TIME_SPEED_HIGH, preset_override_time
                )
            msg = f"Temporary override not available for preset [{preset_mode}]"
            raise HomeAssistantError(msg)
        except AiriosException as ex:
            msg = f"Failed to set temporary preset override: {ex}"
            raise HomeAssistantError(msg) from ex

    @final
    async def async_filter_reset(self) -> bool:
        """Reset the filter dirty flag."""
        dev = await self.api().node(self.modbus_address)
        data = self.coordinator.data.nodes[self.modbus_address]
        ap = AiriosVMDProperty.FILTER_RESET
        if ap not in data:
            msg = f"Property {ap.name} not supported by device {dev!s}."
            raise HomeAssistantError(msg)

        _LOGGER.info("Reset filter dirty flag for node %s", str(dev))
        try:
            if not await dev.set(AiriosVMDProperty.FILTER_RESET, 0):
                msg = "Failed to reset filter dirty flag"
                raise HomeAssistantError(msg)
        except AiriosException as ex:
            msg = f"Failed to reset filter dirty flag: {ex}"
            raise HomeAssistantError(msg) from ex
        return True
