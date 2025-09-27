"""Select platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, PlatformNotReady
from pyairios.constants import VMDBypassMode, VMDOffOnMode
from pyairios.exceptions import AiriosException

from .entity import AiriosEntity

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from pyairios.data_model import AiriosNodeData

    from .coordinator import AiriosDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AiriosSelectEntityDescription(SelectEntityDescription):
    """Airios select description."""

    value_fn: Callable[[Any], str | None] | None = None


BYPASS_MODE_TO_NAME: dict[VMDBypassMode, str] = {
    VMDBypassMode.OPEN: "open",
    VMDBypassMode.CLOSE: "close",
    VMDBypassMode.AUTO: "auto",
    VMDBypassMode.UNKNOWN: "unknown",
}
NAME_TO_BYPASS_MODE = {value: key for (key, value) in BYPASS_MODE_TO_NAME.items()}


def bypass_mode_value_fn(v: VMDBypassMode) -> str | None:
    """Convert bypass mode to select's value."""
    return BYPASS_MODE_TO_NAME.get(v)


OFFON_MODE_TO_NAME: dict[VMDOffOnMode, str] = {
    VMDOffOnMode.OFF: "off",
    VMDOffOnMode.ON: "on",
    VMDOffOnMode.UNKNOWN: "unknown",
}
NAME_TO_OFFON_MODE = {value: key for (key, value) in OFFON_MODE_TO_NAME.items()}


def off_on_value_fn(v: VMDBypassMode) -> str | None:
    """Convert off-on mode to selects value."""
    return OFFON_MODE_TO_NAME.get(v)


# These tuples must match the NodeData defined in pyairios models/
# thus the NodeData must contain a key named like the Description key defined here
# When a new device/rev VMD-02RPS78 is added that doesn't support the following
# selects/functions, or in fact supports more than these: rename or subclass

VMD_02_SELECT_ENTITIES: tuple[AiriosSelectEntityDescription, ...] = (
    AiriosSelectEntityDescription(  # only for vmd_02rps78
        key="bypass_mode",
        translation_key="bypass_mode",
        options=["close", "open", "auto"],
        value_fn=bypass_mode_value_fn,
    ),
)

VMD_07_SELECT_ENTITIES: tuple[AiriosSelectEntityDescription, ...] = (
    AiriosSelectEntityDescription(  # only for vmd_07rps13
        key="basic_ventilation_enable",
        translation_key="basic_vent_enable_sel",
        options=["off", "on"],
        value_fn=off_on_value_fn,
    ),
)

models: dict[str, ModuleType]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selectors."""
    global models  # noqa: PLW0603
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    # fetch model definitions from bridge data
    bridge_id = entry.data[CONF_ADDRESS]  # await coordinator.api.bridge.slave_id()
    models = coordinator.data.nodes[bridge_id]["models"]  # added to pyairios data_model

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

        entities: list[AiriosSelectEntity] = []
        if node["product_id"] is None:
            msg = "Node product ID not available"
            raise PlatformNotReady(msg)

        # only for VMD-x (controllers), not REM
        if node["product_name"].value == "VMD-02RPS78":
            entities.extend(
                [
                    AiriosSelectEntity(description, coordinator, node, via, subentry)
                    for description in VMD_02_SELECT_ENTITIES
                ]
            )
        elif node["product_name"].value == "VMD-07RPS13":
            entities.extend(
                [
                    AiriosSelectEntity(description, coordinator, node, via, subentry)
                    for description in VMD_07_SELECT_ENTITIES
                ]
            )
        async_add_entities(entities, config_subentry_id=subentry_id)


class AiriosSelectEntity(AiriosEntity, SelectEntity):
    """Airios select entity."""

    entity_description: AiriosSelectEntityDescription

    def __init__(
        self,
        description: AiriosSelectEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        node_data: AiriosNodeData,
        via_config_entry: ConfigEntry | None,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize an Airios select entity."""
        super().__init__(description.key, coordinator, node_data, via_config_entry, subentry)
        self.entity_description = description
        self._attr_current_option = None
        self.node_data = node_data

    async def _select_option_internal(self, option: str) -> bool:
        if option == self.current_option:
            return False

        product_name = self.node_data["product_name"].value
        _node = await self.api().node(self.modbus_address)
        ret = VMDOffOnMode.ERROR
        try:
            _node_type = models.get(product_name).Node
            if product_name == "VMD-02RPS78":
                vmd = cast("_node_type", _node)
                if self.entity_description.key == "bypass_mode":
                    bypass_mode = NAME_TO_BYPASS_MODE[option]
                    ret = await vmd.set_bypass_mode(bypass_mode)
            elif product_name == "VMD-07RPS13":
                vmd = cast("_node_type", _node)
                if self.entity_description.key == "basic_ventilation_enable":
                    new_state = NAME_TO_OFFON_MODE[option]
                    ret = await vmd.set_basic_vent_enable(new_state)
        except AiriosException as ex:
            msg = f"Failed to set select option {option}"
            raise HomeAssistantError(msg) from ex
        else:
            return ret

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        update_needed = await self._select_option_internal(option)
        if update_needed:
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        _LOGGER.debug(
            "Handle update for node %s select %s",
            f"{self.rf_address}",
            self.entity_description.key,
        )
        try:
            device = self.coordinator.data.nodes[self.modbus_address]
            result = device[self.entity_description.key]
            _LOGGER.debug(
                "Node %s, select %s, result %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
                result,
            )
            if result is not None and result.value is not None:
                if self.entity_description.value_fn:
                    self._attr_current_option = self.entity_description.value_fn(
                        result.value
                    )
                else:
                    self._attr_current_option = result.value
                self._attr_available = self._attr_current_option is not None
                if result.status is not None:
                    self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError, KeyError):
            _LOGGER.exception(
                "Failed to update node %s select %s",
                f"0x{self.rf_address:08X}",
                self.entity_description.key,
            )
            self._attr_current_option = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()
