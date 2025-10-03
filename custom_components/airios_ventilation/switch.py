"""Switch platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import cast

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from pyairios import AiriosException

from .entity import AiriosEntity

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import Any, ModuleType

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.data_model import AiriosNodeData
    from pyairios.node import AiriosNode

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


# refactor the next set of calls, passing in filter_reset() etc.

async def _base_vent_switch(node: AiriosNode, models: dict[str, ModuleType], newState: bool) -> bool:  # noqa: ARG001
    _name = await node.node_product_name()
    vmd = cast("models[_name.value].Node", node)
    return await vmd.set_basic_vent_enable(newState)


@dataclass(frozen=True, kw_only=True)
class AiriosSwitchEntityDescription(SwitchEntityDescription):
    """Airios switch description."""

    switch_fn: Callable[[AiriosNode], dict[str, ModuleType], Awaitable[bool]]


# These tuples must match the NodeData defined in pyairios models/
# When a new device VMD-xxx is added that doesn't support the following
# switches/functions, or in fact supports more than these: rename or subclass

# VMD_SWITCH_ENTITIES: tuple[AiriosSwitchEntityDescription, ...] = (
#     AiriosSwitchEntityDescription(
#         key="filter_reset",
#         translation_key="filter_reset",
#         switch_fn=_new_switch_function,
#     ),
# )

VMD_07_SWITCH_ENTITIES: tuple[AiriosSwitchEntityDescription, ...] = (
    AiriosSwitchEntityDescription(
        key="basic_ventilation_enable",
        translation_key="basic_vent_enable_sw",
        switch_fn=_base_vent_switch,
    ),
)

models: dict[str, ModuleType]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button platform."""
    global models  # noqa: PLW0603
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data
    api = coordinator.api
    # fetch model definitions from api
    models = await api.airios_models()

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

        entities: list[AiriosSwitchEntity] = []
        product_name = node["product_name"].value

        if product_name is None:
            msg = "Failed to fetch product name from node"
            raise ConfigEntryNotReady(msg)

        # if product_name.startswith("VMD-"):
        #     # check if model supports the function fiets?
        #     entities.extend(
        #         [
        #             AiriosSwitchEntity(description, coordinator, node, via, subentry)
        #             for description in VMD_SWITCH_ENTITIES
        #         ]
        #     )

        if product_name == "VMD-07RPS13":
            # Ventura V1
            entities.extend(
                [
                    AiriosSwitchEntity(description, coordinator, node, via, subentry)
                    for description in VMD_07_SWITCH_ENTITIES
                ]
            )
        async_add_entities(entities, config_subentry_id=subentry_id)


class AiriosSwitchEntity(AiriosEntity, SwitchEntity):
    """Representation of a Airios switch entity."""

    entity_description: AiriosSwitchEntityDescription

    def __init__(
        self,
        description: AiriosSwitchEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        node_data: AiriosNodeData,
        via_config_entry: ConfigEntry | None,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the Airios button entity."""
        super().__init__(
            description.key, coordinator, node_data, via_config_entry, subentry
        )
        self.entity_description = description

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Handle switch on."""
        _LOGGER.debug("Switch %s turned On", self.entity_description.name)
        try:
            node = await self.api().node(self.modbus_address)
            await self.entity_description.switch_fn(node, models, newState=True)
        except AiriosException as ex:
            raise HomeAssistantError from ex

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Handle switch off."""
        _LOGGER.debug("Switch %s turned Off", self.entity_description.name)
        try:
            node = await self.api().node(self.modbus_address)
            await self.entity_description.switch_fn(node, models, newState=False)
        except AiriosException as ex:
            raise HomeAssistantError from ex

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        _LOGGER.debug(
            "Handle update for node %s switch %s",
            f"{self.rf_address}",
            self.entity_description.key,
        )
        try:
            device = self.coordinator.data.nodes[self.modbus_address]
            result = device[self.entity_description.key]
            _LOGGER.debug(
                "Node %s, switch %s, result %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                result,
            )
            if result is not None and result.value is not None:
                self._attr_is_on = result.value
                self._attr_available = self._attr_is_on is not None
                if result.status is not None:
                    self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError):
            _LOGGER.exception(
                "Failed to update node %s switch %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
            )
            self._attr_current_option = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()
