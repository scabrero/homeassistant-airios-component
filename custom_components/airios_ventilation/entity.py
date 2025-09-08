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
    from pyairios.registers import ResultStatus


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

        self.modbus_address = node["slave_id"]
        # in pymodbus>=3.11 keyword "device_id". property name not refactored in pyairios yet

        if node["rf_address"] is None or node["rf_address"].value is None:
            msg = "Node RF address not available"
            raise PlatformNotReady(msg)
        self.rf_address = node["rf_address"].value

        if node["product_name"] is None or node["product_name"].value is None:
            msg = "Node product name not available"
            raise PlatformNotReady(msg)
        product_name = node["product_name"].value

        if node["product_id"] is None:
            msg = "Node product ID not available"
            raise PlatformNotReady(msg)
        if isinstance(node["product_id"], int):
            product_id = node[
                "product_id"
            ]  # BRDG ProductId slipping through despite refactor
        else:
            product_id = node["product_id"].value
        # without .value get TypeError: unsupported format string "BRDG-02R13" (only)
        # but with .value get error: not for int (bin.sensor, number) 2025-09-07 EBR)
        # plus AssertionError: Wrong format for product_id: BRDG-02R13
        # confirm we run latest stable pyairios version??
        assert isinstance(product_id, int), f"Wrong format for product_id: {product_id}"

        if node["sw_version"] is None or node["sw_version"].value is None:
            msg = "Node software version not available"
            raise PlatformNotReady(msg)
        sw_version = node["sw_version"].value

        if self.coordinator.config_entry is None:
            msg = "Unexpected error, config entry not defined"
            raise PlatformNotReady(msg)

        if not product_name:
            product_name = f"0x{self.rf_address:06X}"

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
