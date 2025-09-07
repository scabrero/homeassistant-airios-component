"""Number platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from types import ModuleType
from typing import cast

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import CONF_ADDRESS, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import PlatformNotReady
from pyairios import AiriosException
from pyairios.constants import VMDCapabilities

from .entity import AiriosEntity

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.data_model import AiriosNodeData

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def set_preheater_setpoint(vmd: ModuleType, value: float) -> bool:
    """Set the preheater setpoint."""
    return await vmd.set_preheater_setpoint(value)


async def set_free_ventilation_setpoint(vmd: ModuleType, value: float) -> bool:
    """Set the preheater setpoint."""
    return await vmd.set_free_ventilation_setpoint(value)


async def set_free_ventilation_cooling_offset(vmd: ModuleType, value: float) -> bool:
    """Set the preheater setpoint."""
    return await vmd.set_free_ventilation_cooling_offset(value)


async def set_frost_protection_preheater_setpoint(
    vmd: ModuleType, value: float
) -> bool:
    """Set the preheater setpoint."""
    return await vmd.set_frost_protection_preheater_setpoint(value)


@dataclass(frozen=True, kw_only=True)
class AiriosNumberEntityDescription(NumberEntityDescription):
    """Description of a Airios number entity."""

    set_value_fn: Callable[[ModuleType, float], Awaitable[bool]]


VMD_PREHEATER_NUMBER_ENTITIES: tuple[AiriosNumberEntityDescription, ...] = (
    AiriosNumberEntityDescription(
        key="preheater_setpoint",
        translation_key="preheater_setpoint",
        native_min_value=-20.0,
        native_max_value=50.0,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        set_value_fn=set_preheater_setpoint,
    ),
    AiriosNumberEntityDescription(
        key="frost_protection_preheater_setpoint",
        translation_key="frost_protection_preheater_setpoint",
        native_min_value=-20.0,
        native_max_value=50.0,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        set_value_fn=set_frost_protection_preheater_setpoint,
    ),
)

VMD_FREEVENT_NUMBER_ENTITIES: tuple[AiriosNumberEntityDescription, ...] = (
    AiriosNumberEntityDescription(
        key="free_ventilation_setpoint",
        translation_key="free_ventilation_setpoint",
        native_min_value=0.0,
        native_max_value=30.0,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        set_value_fn=set_free_ventilation_setpoint,
    ),
    AiriosNumberEntityDescription(
        key="free_ventilation_cooling_offset",
        translation_key="free_ventilation_cooling_offset",
        native_min_value=1.0,
        native_max_value=10.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        set_value_fn=set_free_ventilation_cooling_offset,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data
    api = coordinator.api

    # fetch model definitions from bridge data
    bridge_id = entry.data[CONF_ADDRESS]
    models = coordinator.data.nodes[bridge_id]["models"]  # added to pyairios data_model
    prids = coordinator.data.nodes[bridge_id]["product_ids"]
    # also: descriptions

    for modbus_address, node_info in coordinator.data.nodes.items():
        # Find matching subentry
        subentry_id = None
        subentry = None
        via = None
        for se_id, se in entry.subentries.items():
            if se.data[CONF_ADDRESS] == modbus_address:
                subentry_id = se_id
                subentry = se
                via = entry

        entities: list[NumberEntity] = []

        product_id = node_info["product_id"]
        if product_id is None:
            msg = "Failed to fetch product id from node"
            raise PlatformNotReady(msg)

        try:
            for key, _id in prids.items():
                # dict of ids by model_key (names). Can we use node["product_name"] as key?
                if product_id == _id and key.startswith("VMD-"):
                    # only controllers, add is_controller() to model.py?
                    entities.extend(
                        [
                            AiriosNumberEntity(
                                description, coordinator, node_info, via, subentry
                            )
                            for description in VMD_FREEVENT_NUMBER_ENTITIES
                        ]
                    )
                    _mod = models.get(key)
                    vmd = cast(
                        type[str(_mod) + ".Node"],
                        await coordinator.api.node(modbus_address),
                    )
                    capabilities = await vmd.capabilities()
                    if VMDCapabilities.PRE_HEATER_AVAILABLE in capabilities.value:
                        entities.extend(
                            [
                                AiriosNumberEntity(
                                    description, coordinator, node_info, via, subentry
                                )
                                for description in VMD_PREHEATER_NUMBER_ENTITIES
                            ]
                        )
            async_add_entities(entities, config_subentry_id=subentry_id)
        except AiriosException as ex:
            _LOGGER.warning("Failed to setup platform: %s", ex)
            raise PlatformNotReady from ex


class AiriosNumberEntity(AiriosEntity, NumberEntity):
    """Airios number entity."""

    entity_description: AiriosNumberEntityDescription

    def __init__(
        self,
        description: AiriosNumberEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        node: AiriosNodeData,
        via_config_entry: ConfigEntry | None,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize an Airios number entity."""
        super().__init__(description.key, coordinator, node, via_config_entry, subentry)
        self.entity_description = description
        self._attr_current_option = None

    async def _set_value_internal(self, value: float) -> bool:
        if self.entity_description.set_value_fn is None:
            raise NotImplementedError
        node = await self.api().node(self.modbus_address)
        models = self.coordinator.api().bridge.models
        for key, _id in models.items():
            if _id == node.node_product_id():
                _mod = models.get(key)
                vmd = cast(type[str(_mod) + ".Node"], node)
                return await self.entity_description.set_value_fn(vmd, value)
        return False

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        update_needed = await self._set_value_internal(value)
        if update_needed:
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        _LOGGER.debug(
            "Handle update for node %s number %s",
            f"{self.rf_address}",
            self.entity_description.key,
        )
        try:
            device = self.coordinator.data.nodes[self.modbus_address]
            result = device[self.entity_description.key]
            _LOGGER.debug(
                "Node %s, number %s, result %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                result,
            )
            if result is not None and result.value is not None:
                self._attr_native_value = result.value
                self._attr_available = self._attr_native_value is not None
                if result.status is not None:
                    self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError):
            _LOGGER.exception(
                "Failed to update node %s number %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
            )
            self._attr_current_option = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()
