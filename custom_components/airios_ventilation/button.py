"""Button platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.exceptions import HomeAssistantError
from pyairios.exceptions import AiriosException
from pyairios.properties import AiriosVMDProperty

from .entity import (
    AiriosEntity,
    AiriosEntityDescription,
    find_matching_subentry,
)

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.device import AiriosDevice

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def _filter_reset(dev: AiriosDevice) -> bool:
    return await dev.set(AiriosVMDProperty.FILTER_RESET, 0)


@dataclass(frozen=True, kw_only=True)
class AiriosButtonEntityDescription(AiriosEntityDescription, ButtonEntityDescription):
    """Airios binary sensor description."""

    press_fn: Callable[[AiriosDevice], Awaitable[bool]]


VMD_BUTTON_ENTITIES: tuple[AiriosButtonEntityDescription, ...] = (
    AiriosButtonEntityDescription(
        ap=AiriosVMDProperty.FILTER_RESET,
        key=AiriosVMDProperty.FILTER_RESET.name.casefold(),
        translation_key="filter_reset",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=_filter_reset,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 # pylint: disable=unused-argument
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    for modbus_address, node in coordinator.data.nodes.items():
        subentry = find_matching_subentry(entry, modbus_address)
        entities: list[AiriosButtonEntity] = [
            AiriosButtonEntity(description, coordinator, modbus_address, subentry)
            for description in VMD_BUTTON_ENTITIES
            if description.ap in node
        ]
        subentry_id = subentry.subentry_id if subentry else None
        async_add_entities(entities, config_subentry_id=subentry_id)


class AiriosButtonEntity(  # pyright: ignore[reportIncompatibleVariableOverride]
    AiriosEntity,
    ButtonEntity,
):
    """Representation of a Airios button entity."""

    entity_description: AiriosButtonEntityDescription

    def __init__(
        self,
        description: AiriosButtonEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        modbus_address: int,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the Airios button entity."""
        super().__init__(description.key, coordinator, modbus_address, subentry)
        self.entity_description = description  # type: ignore[override]

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.debug("Button %s pressed", self.entity_description.key)
        try:
            dev = await self.api().node(self.modbus_address)
            await self.entity_description.press_fn(dev)
        except AiriosException as ex:
            raise HomeAssistantError from ex
