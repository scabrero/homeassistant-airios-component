"""Base entity for the Airios integration."""

from __future__ import annotations

import typing

from homeassistant.exceptions import ConfigEntryNotReady, PlatformNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import AiriosDataUpdateCoordinator

if typing.TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from pyairios import Airios
    from pyairios.data_model import AiriosNodeData
    from pyairios.registers import Result, ResultStatus


class AiriosEntity(CoordinatorEntity[AiriosDataUpdateCoordinator]):
    """Airios base entity."""

    _attr_has_entity_name = True
    _unavailable_logged: bool = False

    rf_address: int
    modbus_address: int

    def __init__(
        self,
        key: str,
        coordinator: AiriosDataUpdateCoordinator,
        node: AiriosNodeData,
        via_config_entry: ConfigEntry | None,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        def node_attrib(attrib: Result, attrib_name: str) -> str | int:
            if attrib is None or (not isinstance(attrib, int) and attrib.value is None):
                _msg = f"Node {attrib_name} not available"
                raise PlatformNotReady(_msg)
            if isinstance(attrib, int):
                return attrib
            return attrib.value

        self.modbus_address = node["slave_id"]
        # in pymodbus>=3.11 keyword "device_id". prop name not refactored in pyairios

        result = node["rf_address"]
        self.rf_address = node_attrib(result, "RF address")

        result = node["product_name"]
        product_name = node_attrib(result, "product name")

        result = node["product_id"]
        product_id = node_attrib(result, "product ID")

        result = node["sw_version"]
        sw_version = node_attrib(result, "software version")

        if self.coordinator.config_entry is None:
            msg = "Unexpected error, config entry not defined"
            raise PlatformNotReady(msg)

        if not product_name:
            product_name = f"0x{self.rf_address:06X}"

        name: str | None = None
        if subentry is None:
            name = product_name
        else:
            name = subentry.data.get("name")
            if name is None:
                msg = "Failed to get name from subentry"
                raise ConfigEntryNotReady(msg)

        self._attr_device_info = DeviceInfo(
            name=name,
            serial_number=f"0x{self.rf_address:06X}",
            identifiers={(DOMAIN, str(self.rf_address))},
            manufacturer=DEFAULT_NAME,
            model=product_name,
            model_id=f"0x{product_id:08X}",
            sw_version=f"0x{sw_version:04X}",
        )

        if via_config_entry is not None:
            if via_config_entry.unique_id is None:
                msg = "Failed to get config entry unique id"
                raise ConfigEntryNotReady(msg)
            self._attr_device_info["via_device"] = (DOMAIN, via_config_entry.unique_id)

        self._attr_unique_id = f"{self.rf_address}-{key}"

    def api(self) -> Airios:
        """Return the Airios API."""
        return self.coordinator.api

    def set_extra_state_attributes_internal(self, status: ResultStatus) -> None:
        """Set extra state attributes."""
        self._attr_extra_state_attributes = {
            "age": str(status.age),
            "source": str(status.source),
            "flags": str(status.flags),
        }
