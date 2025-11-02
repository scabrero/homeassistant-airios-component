"""Switch platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
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


async def _base_vent_switch(vmd: AiriosDevice, value: int) -> bool:
    return await vmd.set(AiriosVMDProperty.BASIC_VENTILATION_ENABLE, value)


@dataclass(frozen=True, kw_only=True)
class AiriosSwitchEntityDescription(AiriosEntityDescription, SwitchEntityDescription):
    """Airios switch description."""

    set_value_fn: Callable[[AiriosDevice, int], Awaitable[bool]]


SWITCH_ENTITIES: tuple[AiriosSwitchEntityDescription, ...] = (
    AiriosSwitchEntityDescription(
        ap=AiriosVMDProperty.BASIC_VENTILATION_ENABLE,
        key=AiriosVMDProperty.BASIC_VENTILATION_ENABLE.name.casefold(),
        translation_key="basic_vent_enable_sw",
        set_value_fn=_base_vent_switch,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 # pylint: disable=unused-argument
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    for modbus_address, node in coordinator.data.nodes.items():
        subentry = find_matching_subentry(entry, modbus_address)
        entities: list[AiriosSwitchEntity] = [
            AiriosSwitchEntity(description, coordinator, modbus_address, subentry)
            for description in SWITCH_ENTITIES
            if description.ap in node
        ]
        subentry_id = subentry.subentry_id if subentry else None
        async_add_entities(entities, config_subentry_id=subentry_id)


class AiriosSwitchEntity(  # pyright: ignore[reportIncompatibleVariableOverride]
    AiriosEntity,
    SwitchEntity,
):
    """Representation of a Airios switch entity."""

    entity_description: AiriosSwitchEntityDescription

    def __init__(
        self,
        description: AiriosSwitchEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        modbus_address: int,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize an Airios switch entity."""
        super().__init__(description.key, coordinator, modbus_address, subentry)
        self.entity_description = description  # type: ignore[override]

    async def _set_value_internal(self, value: int) -> bool:
        if self.entity_description.set_value_fn is None:
            raise NotImplementedError
        dev = await self.api().node(self.modbus_address)
        return await self.entity_description.set_value_fn(dev, value)

    async def async_turn_on(
        self,
        **kwargs: Any,  # noqa: ARG002 # pylint: disable=unused-argument
    ) -> None:
        """Handle switch on."""
        _LOGGER.debug("Switch %s turned On", self.entity_description.name)
        update_needed = await self._set_value_internal(1)
        if update_needed:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(
        self,
        **kwargs: Any,  # noqa: ARG002 # pylint: disable=unused-argument
    ) -> None:
        """Handle switch off."""
        _LOGGER.debug("Switch %s turned Off", self.entity_description.name)
        update_needed = await self._set_value_internal(0)
        if update_needed:
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        try:
            result = self.fetch_result()
            self._attr_is_on = result.value
            self._attr_available = self._attr_is_on is not None
            if result.status is not None:
                self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError) as ex:
            _LOGGER.info(
                "Failed to update switch entity for node=%s, property=%s: %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                ex,
            )
            self._attr_is_on = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()
