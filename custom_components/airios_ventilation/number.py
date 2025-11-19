"""Number platform for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    EntityCategory,
    UnitOfTemperature,
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


async def set_preheater_setpoint(vmd: AiriosDevice, value: float) -> bool:
    """Set the preheater setpoint."""
    return await vmd.set(AiriosVMDProperty.PREHEATER_SETPOINT, value)


async def set_free_ventilation_setpoint(vmd: AiriosDevice, value: float) -> bool:
    """Set the preheater setpoint."""
    return await vmd.set(AiriosVMDProperty.FREE_VENTILATION_HEATING_SETPOINT, value)


async def set_free_ventilation_cooling_offset(vmd: AiriosDevice, value: float) -> bool:
    """Set the preheater setpoint."""
    return await vmd.set(AiriosVMDProperty.FREE_VENTILATION_COOLING_OFFSET, value)


async def set_frost_protection_preheater_setpoint(
    vmd: AiriosDevice, value: float
) -> bool:
    """Set the preheater setpoint."""
    return await vmd.set(AiriosVMDProperty.FROST_PROTECTION_PREHEATER_SETPOINT, value)


async def set_co2_setpoint(vmd: AiriosDevice, value: float) -> bool:
    """Set the CO2 setpoint."""
    return await vmd.set(AiriosVMDProperty.CO2_CONTROL_SETPOINT, value)


@dataclass(frozen=True, kw_only=True)
class AiriosNumberEntityDescription(AiriosEntityDescription, NumberEntityDescription):
    """Description of a Airios number entity."""

    set_value_fn: Callable[[AiriosDevice, float], Awaitable[bool]]


NUMBER_ENTITIES: tuple[AiriosNumberEntityDescription, ...] = (
    AiriosNumberEntityDescription(
        ap=AiriosVMDProperty.PREHEATER_SETPOINT,
        key=AiriosVMDProperty.PREHEATER_SETPOINT.name.casefold(),
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
        ap=AiriosVMDProperty.FROST_PROTECTION_PREHEATER_SETPOINT,
        key=AiriosVMDProperty.FROST_PROTECTION_PREHEATER_SETPOINT.name.casefold(),
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
    AiriosNumberEntityDescription(
        ap=AiriosVMDProperty.FREE_VENTILATION_HEATING_SETPOINT,
        key=AiriosVMDProperty.FREE_VENTILATION_HEATING_SETPOINT.name.casefold(),
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
        ap=AiriosVMDProperty.FREE_VENTILATION_COOLING_OFFSET,
        key=AiriosVMDProperty.FREE_VENTILATION_COOLING_OFFSET.name.casefold(),
        translation_key="free_ventilation_cooling_offset",
        native_min_value=1.0,
        native_max_value=10.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        set_value_fn=set_free_ventilation_cooling_offset,
    ),
    # VMD07-RP13 specific
    AiriosNumberEntityDescription(
        ap=AiriosVMDProperty.CO2_CONTROL_SETPOINT,
        key=AiriosVMDProperty.CO2_CONTROL_SETPOINT.name.casefold(),
        translation_key="co2_setpoint",
        native_min_value=400,
        native_max_value=2300,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        set_value_fn=set_co2_setpoint,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 # pylint: disable=unused-argument
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator: AiriosDataUpdateCoordinator = entry.runtime_data

    for modbus_address, node in coordinator.data.nodes.items():
        subentry = find_matching_subentry(entry, modbus_address)
        entities: list[AiriosNumberEntity] = [
            AiriosNumberEntity(description, coordinator, modbus_address, subentry)
            for description in NUMBER_ENTITIES
            if description.ap in node
        ]
        subentry_id = subentry.subentry_id if subentry else None
        async_add_entities(entities, config_subentry_id=subentry_id)


class AiriosNumberEntity(  # pyright: ignore[reportIncompatibleVariableOverride]
    AiriosEntity,
    NumberEntity,
):
    """Airios number entity."""

    entity_description: AiriosNumberEntityDescription

    def __init__(
        self,
        description: AiriosNumberEntityDescription,
        coordinator: AiriosDataUpdateCoordinator,
        modbus_address: int,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize a Airios number entity."""
        super().__init__(description.key, coordinator, modbus_address, subentry)
        self.entity_description = description  # type: ignore[override]
        self._attr_current_option = None

    async def _set_value_internal(self, value: float) -> bool:
        if self.entity_description.set_value_fn is None:
            raise NotImplementedError
        dev = await self.api().node(self.modbus_address)
        return await self.entity_description.set_value_fn(dev, value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        update_needed = await self._set_value_internal(value)
        if update_needed:
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle update data from the coordinator."""
        try:
            result = self.fetch_result()
            self._attr_native_value = result.value
            self._attr_available = self._attr_native_value is not None
            if result.status is not None:
                self.set_extra_state_attributes_internal(result.status)
        except (TypeError, ValueError) as ex:
            _LOGGER.info(
                "Failed to update number entity for node=%s, property=%s: %s",
                f"0x{self.rf_address:06X}",
                self.entity_description.key,
                ex,
            )
            self._attr_current_option = None
            self._attr_available = False
        finally:
            self.async_write_ha_state()
