"""Fan platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from types import ModuleType
from typing import Any, cast, final

from homeassistant.components.fan import (
    FanEntity,
    FanEntityDescription,
    FanEntityFeature,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    HomeAssistantError,
    PlatformNotReady,
)
from homeassistant.helpers import entity_platform
from pyairios import AiriosException
from pyairios.constants import (
    VMDCapabilities,
    VMDRequestedVentilationSpeed,
    VMDVentilationSpeed,
)

from .entity import AiriosEntity
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
    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.data_model import AiriosNodeData

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

VMD_FAN_ENTITIES: tuple[FanEntityDescription, ...] = (
    FanEntityDescription(
        key="ventilation_speed",
        translation_key="ventilation_speed",
    ),
)

models: dict[str, ModuleType]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: AiriosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the fan entities."""
    global models
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    # fetch model definitions from bridge data
    bridge_id = entry.data[CONF_ADDRESS]
    models = coordinator.data.nodes[bridge_id]["models"]  # added to pyairios data_model
    prids = coordinator.data.nodes[bridge_id]["product_ids"]

    for modbus_address, node in coordinator.data.nodes.items():
        # Find matching subentry
        subentry_id = None
        subentry = None
        via = None
        for se_id, se in entry.subentries.items():
            if se.data[CONF_ADDRESS] == modbus_address:
                subentry_id = se_id
                subentry = se
                via = entry

        entities: list[FanEntity] = []

        product_id = node["product_id"]
        if product_id is None:
            msg = "Failed to fetch product id from node"
            raise PlatformNotReady(msg)

        try:
            # lookup node model family by key # compare to pyairios/cli.py
            for key, _id in prids.items():
                # dict of ids by model_key (names). Can we use node["product_name"] as key?

                if product_id == _id and key.startswith("VMD-"):
                    # only for controllers. Add is_controller() flag to model.py?
                    _mod = models.get(key)
                    vmd = cast(
                        type[str(_mod) + ".Node"],
                        await coordinator.api.node(modbus_address),
                    )
                    result = await vmd.capabilities()
                    if result is not None:
                        capabilities = result.value
                    else:
                        capabilities = (
                            VMDCapabilities.OFF_CAPABLE  # NO_CAPABLE
                        )  # DEBUG EBR waiting for pyairios lib reinstall, silence log error
                    entities.extend(
                        [
                            AiriosFanEntity(
                                description,
                                coordinator,
                                node,
                                capabilities,
                                via,
                                subentry,
                            )
                            for description in VMD_FAN_ENTITIES
                        ]
                    )
            async_add_entities(entities, config_subentry_id=subentry_id)
        except AiriosException as ex:
            _LOGGER.warning("Failed to setup platform: %s", ex)
            raise PlatformNotReady from ex

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


class AiriosFanEntity(AiriosEntity, FanEntity):
    """Airios fan entity."""

    _attr_name = None
    _attr_supported_features = FanEntityFeature.PRESET_MODE
    _node_class: ModuleType

    def __init__(  # noqa: PLR0913
        self,
        description: FanEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        node: AiriosNodeData,
        capabilities: VMDCapabilities,
        via_config_entry: ConfigEntry | None,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the Airios fan entity."""
        super().__init__(description.key, coordinator, node, via_config_entry, subentry)
        self.entity_description = description
        self._node_class = models[node["product_name"].value].Node

        _LOGGER.info(
            "Fan for node %s@%s capable of %s",
            node["product_name"],
            node["slave_id"],
            capabilities,  # not all Airios fans support a capabilities register
        )

        self._attr_preset_modes = [
            PRESET_NAMES[VMDVentilationSpeed.LOW],
            PRESET_NAMES[VMDVentilationSpeed.MID],
            PRESET_NAMES[VMDVentilationSpeed.HIGH],
        ]

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
        percentage: int | None = None,  # noqa: ARG002
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
            node = cast("self._node_class", await self.api().node(self.modbus_address))
            vmd_speed = PRESET_TO_VMD_SPEED[preset_mode]

            # Handle temporary overrides
            if preset_mode in (
                PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_LOW],
                PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_MID],
                PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_HIGH],
            ):
                return await node.set_ventilation_speed_override_time(vmd_speed, 60)
            return await node.set_ventilation_speed(vmd_speed)
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
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """Turn on the fan."""
        update_needed = await self._turn_on_internal(percentage, preset_mode)
        if update_needed:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
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
        _LOGGER.debug(
            "Handle update for node %s fan %s",
            f"{self.rf_address}",
            self.entity_description.key,
        )
        try:
            device = self.coordinator.data.nodes[self.modbus_address]
            result = device[self.entity_description.key]
            _LOGGER.debug(
                "Node %s, fan %s, result %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                result,
            )
            if result is not None and result.value is not None:
                self._attr_preset_mode = PRESET_NAMES[result.value]
            if result is not None and result.status is not None:
                self.set_extra_state_attributes_internal(result.status)
            self._attr_available = self._attr_preset_mode is not None
        except (TypeError, ValueError):
            _LOGGER.exception(
                "Failed to update node %s fan %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
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
        node = cast("self._node_class", await self.api().node(self.modbus_address))
        msg = (
            "Setting fans speeds for away preset on node "
            f"{node} to: supply={supply_fan_speed}%%, exhaust={exhaust_fan_speed}%%"
        )
        _LOGGER.info(msg)
        try:
            if not await node.set_preset_standby_fan_speed_supply(supply_fan_speed):
                msg = f"Failed to set supply fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
            if not await node.set_preset_standby_fan_speed_exhaust(exhaust_fan_speed):
                msg = f"Failed to set exhaust fan speed to {supply_fan_speed}"
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
        node = cast("self._node_class", await self.api().node(self.modbus_address))
        msg = (
            "Setting fans speeds for low preset on node "
            f"{node} to: supply={supply_fan_speed}%%, exhaust={exhaust_fan_speed}%%",
        )
        _LOGGER.info(msg)
        try:
            if not await node.set_preset_low_fan_speed_supply(supply_fan_speed):
                msg = f"Failed to set supply fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
            if not await node.set_preset_low_fan_speed_exhaust(exhaust_fan_speed):
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
        node = cast("self._node_class", await self.api().node(self.modbus_address))
        msg = (
            "Setting fans speeds for medium preset on node "
            f"{node} to: supply={supply_fan_speed}%%, exhaust={exhaust_fan_speed}%%",
        )
        _LOGGER.info(msg)
        try:
            if not await node.set_preset_medium_fan_speed_supply(supply_fan_speed):
                msg = f"Failed to set supply fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
            if not await node.set_preset_medium_fan_speed_exhaust(exhaust_fan_speed):
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
        node = cast("self._node_class", await self.api().node(self.modbus_address))
        msg = (
            "Setting fans speeds for high preset on node "
            f"{node} to: supply={supply_fan_speed}%%, exhaust={exhaust_fan_speed}%%",
        )
        _LOGGER.info(msg)
        try:
            if not await node.set_preset_high_fan_speed_supply(supply_fan_speed):
                msg = f"Failed to set supply fan speed to {supply_fan_speed}"
                raise HomeAssistantError(msg)
            if not await node.set_preset_high_fan_speed_exhaust(exhaust_fan_speed):
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
        if preset_mode == PRESET_NAMES[VMDVentilationSpeed.LOW]:
            preset_mode = PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_LOW]
        elif preset_mode == PRESET_NAMES[VMDVentilationSpeed.MID]:
            preset_mode = PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_MID]
        elif preset_mode == PRESET_NAMES[VMDVentilationSpeed.HIGH]:
            preset_mode = PRESET_NAMES[VMDVentilationSpeed.OVERRIDE_HIGH]
        else:
            msg = f"Temporary override not available for preset [{preset_mode}]"
            raise HomeAssistantError(msg)
        vmd_speed = PRESET_TO_VMD_SPEED[preset_mode]
        node = cast("self._node_class", await self.api().node(self.modbus_address))
        # result = await node.capabilities()
        caps = 0  # EBR debug was: result.value
        if VMDCapabilities.TIMER_CAPABLE not in caps:
            msg = f"Device {node!s} does not support preset temporary override"
            raise HomeAssistantError(msg)
        _LOGGER.info(
            "Setting preset mode on node %s to: %s for %s minutes",
            str(node),
            vmd_speed,
            preset_override_time,
        )
        try:
            if not await node.set_ventilation_speed_override_time(
                vmd_speed, preset_override_time
            ):
                msg = "Failed to set temporary preset override"
                raise HomeAssistantError(msg)
        except AiriosException as ex:
            msg = f"Failed to set temporary preset override: {ex}"
            raise HomeAssistantError(msg) from ex
        return True

    @final
    async def async_filter_reset(self) -> bool:
        """Reset the filter dirty flag."""
        node = cast("self._node_class", await self.api().node(self.modbus_address))
        _LOGGER.info("Reset filter dirty flag for node %s", str(node))
        try:
            if not await node.filter_reset():
                msg = "Failed to reset filter dirty flag"
                raise HomeAssistantError(msg)
        except AiriosException as ex:
            msg = f"Failed to reset filter dirty flag: {ex}"
            raise HomeAssistantError(msg) from ex
        return True
