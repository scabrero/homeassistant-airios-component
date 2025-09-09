"""Button platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from types import ModuleType
from typing import cast

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from pyairios import AiriosException

from .entity import AiriosEntity

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.data_model import AiriosNodeData
    from pyairios.node import AiriosNode

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def _filter_reset(node: AiriosNode, models: dict[str, ModuleType]) -> bool:
    for key, _id in models.items():
        if _id == node.node_product_id():
            _mod = models.get(key)
            vmd = cast(type[str(_mod) + ".Node"], node)
            return await vmd.filter_reset()
    return False


@dataclass(frozen=True, kw_only=True)
class AiriosButtonEntityDescription(ButtonEntityDescription):
    """Airios binary sensor description."""

    press_fn: Callable[[AiriosNode], dict[str, ModuleType], Awaitable[bool]]


# These tuples must match the NodeData defined in pyairios models/
# When a new device VMD-xxx is added that doesn't support the following buttons/functions,
# or in fact supports more than these: rename or subclass

VMD_BUTTON_ENTITIES: tuple[AiriosButtonEntityDescription, ...] = (
    AiriosButtonEntityDescription(
        key="filter_reset",
        translation_key="filter_reset",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=_filter_reset,
    ),
)

models: dict[str, ModuleType]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button platform."""
    global models
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    # fetch model definitions from bridge data
    bridge_id = entry.data[CONF_ADDRESS]
    models = coordinator.data.nodes[bridge_id]["models"]  # added in pyairios data_model
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

        entities: list[AiriosButtonEntity] = []

        product_id = node["product_id"]
        if product_id is None:
            msg = "Failed to fetch product id from node"
            raise ConfigEntryNotReady(msg)

        for key, _id in prids.items():
            # dict of ids by model_key (names). Can we use node["product_name"] as key?
            if product_id == _id and key.startswith("VMD-"):
                # TODO check if it supports reset_filter
                entities.extend(
                    [
                        AiriosButtonEntity(
                            description, coordinator, node, via, subentry
                        )
                        for description in VMD_BUTTON_ENTITIES
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
        node: AiriosNodeData,
        via_config_entry: ConfigEntry | None,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the Airios button entity."""
        super().__init__(description.key, coordinator, node, via_config_entry, subentry)
        self.entity_description = description

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.debug("Button %s pressed", self.entity_description.name)
        try:
            node = await self.api().node(self.modbus_address)
            await self.entity_description.press_fn(node, models)
        except AiriosException as ex:
            raise HomeAssistantError from ex
