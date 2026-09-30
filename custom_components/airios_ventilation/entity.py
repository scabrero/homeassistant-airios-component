"""Base entity for the Airios integration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass

from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ConfigEntryNotReady, PlatformNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pyairios.properties import AiriosBaseProperty, AiriosDeviceProperty

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import AiriosDataUpdateCoordinator

if typing.TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from pyairios import Airios
    from pyairios.registers import Result, ResultStatus


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AiriosEntityDescription:
    """Base class for Airios entities descriptions."""

    ap: AiriosBaseProperty


def find_matching_subentry(
    entry: ConfigEntry, modbus_address: int
) -> ConfigSubentry | None:
    """Find matching subentry for entities."""
    for se in entry.subentries.values():
        if se.data[CONF_ADDRESS] == modbus_address:
            return se
    return None


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
        modbus_address: int,
        subentry: ConfigSubentry | None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        self.modbus_address = modbus_address

        data = coordinator.data.nodes[modbus_address]

        if AiriosDeviceProperty.RF_ADDRESS not in data:
            msg = "Node RF address not available"
            raise PlatformNotReady(msg)
        self.rf_address = data[AiriosDeviceProperty.RF_ADDRESS].value

        if AiriosDeviceProperty.PRODUCT_NAME not in data:
            msg = "Node product name not available"
            raise PlatformNotReady(msg)
        product_name = data[AiriosDeviceProperty.PRODUCT_NAME].value

        if AiriosDeviceProperty.PRODUCT_ID not in data:
            msg = "Node product ID not available"
            raise PlatformNotReady(msg)
        product_id = data[AiriosDeviceProperty.PRODUCT_ID].value

        if AiriosDeviceProperty.SOFTWARE_VERSION not in data:
            msg = "Node software version not available"
            raise PlatformNotReady(msg)
        sw_version = data[AiriosDeviceProperty.SOFTWARE_VERSION].value

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

        if (
            (r1 := coordinator.data.nodes.get(coordinator.data.bridge_key))
            and (r2 := r1.get(AiriosDeviceProperty.RF_ADDRESS))
            and (brdg_rf_address := r2.value)
            and (brdg_rf_address != self.rf_address)
        ):
            self._attr_device_info["via_device"] = (DOMAIN, str(brdg_rf_address))

        self._attr_unique_id = f"{self.rf_address}-{key}"
        _LOGGER.debug("Entity %s has unique id %s", key, self._attr_unique_id)

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

    def fetch_result(self) -> Result:
        """Fetch result for entity."""
        _LOGGER.debug(
            "Updating node=%s, property=%s",
            f"{self.rf_address}:08X",
            self.entity_description.key,
        )

        if not isinstance(self.entity_description, AiriosEntityDescription):
            msg = "Expected Airios entity description"
            raise TypeError(msg)

        ap = typing.cast("AiriosEntityDescription", self.entity_description).ap
        data = self.coordinator.data.nodes[self.modbus_address]
        result = data[ap]
        _LOGGER.debug(
            "Node=%s, property=%s, result=%s",
            f"0x{self.rf_address:08X}",
            self.entity_description.key,
            result,
        )
        if result is None or result.value is None:
            msg = f"{self.entity_description.key} result not exists"
            raise ValueError(msg)
        return result
