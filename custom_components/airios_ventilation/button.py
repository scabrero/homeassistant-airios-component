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
from pyairios.constants import ProductId

from .entity import AiriosEntity

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.data_model import AiriosNodeData
    from pyairios.node import AiriosNode
    from pyairios.models.vmd_02rps78 import VmdNode  # TODO import VMD02RPS78 as dict modules[] from bridge

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def _filter_reset(node: AiriosNode) -> bool:
    vmd = cast(VmdNode, node)
    # TODO pass in the coordinator to select model from id?
    return await vmd.filter_reset()


@dataclass(frozen=True, kw_only=True)
class AiriosButtonEntityDescription(ButtonEntityDescription):
    """Airios binary sensor description."""

    press_fn: Callable[[AiriosNode], Awaitable[bool]]


VMD_BUTTON_ENTITIES: tuple[AiriosButtonEntityDescription, ...] = (
    AiriosButtonEntityDescription(
        key="filter_reset",
        translation_key="filter_reset",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=_filter_reset,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

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

        result = node["product_id"]
        if result is None or result.value is None:
            msg = "Failed to fetch product id from node"
            raise ConfigEntryNotReady(msg)
        if result.value == ProductId.VMD_02RPS78:
            entities.extend(
                [
                    AiriosButtonEntity(description, coordinator, node, via, subentry)
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
            await self.entity_description.press_fn(node)
        except AiriosException as ex:
            raise HomeAssistantError from ex
