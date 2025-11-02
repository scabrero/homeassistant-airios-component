"""Select platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from pyairios.constants import VMDBypassMode
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
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.device import AiriosDevice

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AiriosSelectEntityDescription(AiriosEntityDescription, SelectEntityDescription):
    """Airios select description."""

    value_fn: Callable[[Any], str | None]
    set_value_fn: Callable[[AiriosDevice, str], Awaitable[bool]]


BYPASS_MODE_TO_NAME: dict[VMDBypassMode, str] = {
    VMDBypassMode.OPEN: "open",
    VMDBypassMode.CLOSE: "close",
    VMDBypassMode.AUTO: "auto",
    VMDBypassMode.UNKNOWN: "unknown",
}
NAME_TO_BYPASS_MODE = {value: key for (key, value) in BYPASS_MODE_TO_NAME.items()}


async def _set_bypass_mode_fn(dev: AiriosDevice, option: str) -> bool:
    bypass_mode = NAME_TO_BYPASS_MODE[option]
    return await dev.set(AiriosVMDProperty.REQUESTED_BYPASS_MODE, bypass_mode)


SELECT_ENTITIES: tuple[AiriosSelectEntityDescription, ...] = (
    AiriosSelectEntityDescription(
        ap=AiriosVMDProperty.BYPASS_MODE,
        key=AiriosVMDProperty.BYPASS_MODE.name.casefold(),
        translation_key="bypass_mode",
        options=["close", "open", "auto"],
        value_fn=BYPASS_MODE_TO_NAME.get,
        set_value_fn=_set_bypass_mode_fn,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 # pylint: disable=unused-argument
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selectors."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    for modbus_address, node in coordinator.data.nodes.items():
        subentry = find_matching_subentry(entry, modbus_address)
        entities: list[AiriosSelectEntity] = [
            AiriosSelectEntity(description, coordinator, modbus_address, subentry)
            for description in SELECT_ENTITIES
            if description.ap in node
        ]
        subentry_id = subentry.subentry_id if subentry else None
        async_add_entities(entities, config_subentry_id=subentry_id)


class AiriosSelectEntity(  # pyright: ignore[reportIncompatibleVariableOverride]
    AiriosEntity,
    SelectEntity,
):
    """Airios select entity."""

    entity_description: AiriosSelectEntityDescription

    def __init__(
        self,
        description: AiriosSelectEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        modbus_address: int,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize a Airios select entity."""
        super().__init__(description.key, coordinator, modbus_address, subentry)
        self.entity_description = description  # type: ignore[override]
        self._attr_current_option = None

    async def _select_option_internal(self, option: str) -> bool:
        if option == self.current_option:
            return False

        try:
            dev = await self.api().node(self.modbus_address)
            ret = await self.entity_description.set_value_fn(dev, option)
        except AiriosException as ex:
            msg = f"Failed to set {self.entity_description.key} to {option}"
            raise HomeAssistantError(msg) from ex
        return ret

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        update_needed = await self._select_option_internal(option)
        if update_needed:
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        try:
            result = self.fetch_result()
            self._attr_current_option = self.entity_description.value_fn(result.value)
            self._attr_available = self._attr_current_option is not None
            if result.status is not None:
                self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError) as ex:
            _LOGGER.info(
                "Failed to update select entity for node=%s, property=%s: %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                ex,
            )
            self._attr_current_option = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()
