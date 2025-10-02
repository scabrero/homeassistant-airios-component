"""Button platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import cast

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from pyairios import AiriosException
from pyairios.constants import VMDRequestedVentilationSpeed

from .entity import AiriosEntity

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import ModuleType

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.data_model import AiriosNodeData
    from pyairios.node import AiriosNode

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


# refactor the next set of calls, passing in filter_reset() etc.


async def _filter_reset(node: AiriosNode, models: dict[str, ModuleType]) -> bool:  # noqa: ARG001
    _name = await node.node_product_name()
    vmd = cast("models[_name.value].Node", node)
    return await vmd.filter_reset()


async def _temp_boost(node: AiriosNode, models: dict[str, ModuleType]) -> bool:  # noqa: ARG001
    _name = await node.node_product_name()
    vmd = cast("models[_name.value].Node", node)
    return await vmd.set_ventilation_speed(VMDRequestedVentilationSpeed.HIGH)


@dataclass(frozen=True, kw_only=True)
class AiriosButtonEntityDescription(ButtonEntityDescription):
    """Airios binary sensor description."""

    press_fn: Callable[[AiriosNode], dict[str, ModuleType], Awaitable[bool]]


# These tuples must match the NodeData defined in pyairios models/
# When a new device VMD-xxx is added that doesn't support the following
# buttons/functions, or in fact supports more than these: rename or subclass

VMD_BUTTON_ENTITIES: tuple[AiriosButtonEntityDescription, ...] = (
    AiriosButtonEntityDescription(
        key="filter_reset",
        translation_key="filter_reset",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=_filter_reset,
    ),
)

VMD_07_BUTTON_ENTITIES: tuple[AiriosButtonEntityDescription, ...] = (
    AiriosButtonEntityDescription(
        key="temp_boost",
        translation_key="temp_boost",
        press_fn=_temp_boost,
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

        entities: list[AiriosButtonEntity] = []
        product_name = node["product_name"].value

        if product_name is None:
            msg = "Failed to fetch product name from node"
            raise ConfigEntryNotReady(msg)

        if product_name.startswith("VMD-"):
            # check if model supports reset_filter
            entities.extend(
                [
                    AiriosButtonEntity(description, coordinator, node, via, subentry)
                    for description in VMD_BUTTON_ENTITIES
                ]
            )

        if product_name == "VMD-07RPS13":
            # Ventura V1
            entities.extend(
                [
                    AiriosButtonEntity(description, coordinator, node, via, subentry)
                    for description in VMD_07_BUTTON_ENTITIES
                ]
            )
        async_add_entities(entities, config_subentry_id=subentry_id)


class AiriosButtonEntity(AiriosEntity, ButtonEntity):
    """Representation of a Airios button entity."""

    entity_description: AiriosButtonEntityDescription

    def __init__(
        self,
        description: AiriosButtonEntityDescription,
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

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.debug("Button %s pressed", self.entity_description.name)
        try:
            node = await self.api().node(self.modbus_address)
            await self.entity_description.press_fn(node, models)
        except AiriosException as ex:
            raise HomeAssistantError from ex
