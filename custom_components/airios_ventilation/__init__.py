"""The Airios integration."""

from __future__ import annotations

import logging
import typing

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_DEVICE,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TYPE,
    Platform,
)
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from pyairios import Airios, AiriosRtuTransport, AiriosTcpTransport

from .const import DEFAULT_NAME, DEFAULT_SCAN_INTERVAL, DOMAIN, BridgeType
from .coordinator import AiriosDataUpdateCoordinator

if typing.TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


type AiriosConfigEntry = ConfigEntry[AiriosDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AiriosConfigEntry) -> bool:
    """Set up Airios from a config entry."""
    bridge_type = entry.data[CONF_TYPE]
    if bridge_type == BridgeType.SERIAL:
        device = entry.data[CONF_DEVICE]
        transport = AiriosRtuTransport(device)
    elif bridge_type == BridgeType.NETWORK:
        host = entry.data[CONF_HOST]
        port = entry.data[CONF_PORT]
        transport = AiriosTcpTransport(host, port)
    else:
        msg = f"Unexpected bridge type {bridge_type}"
        raise ConfigEntryError(msg)

    modbus_address = entry.data[CONF_ADDRESS]
    api = Airios(transport, modbus_address)

    update_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = AiriosDataUpdateCoordinator(hass, api, update_interval)
    await coordinator.async_config_entry_first_refresh()

    bridge_rf_address = await api.bridge.node_rf_address()
    if bridge_rf_address is None or bridge_rf_address.value is None:
        msg = "Failed to get bridge RF address"
        raise ConfigEntryNotReady(msg)
    bridge_rf_address = bridge_rf_address.value

    if entry.unique_id != str(bridge_rf_address):
        message = (
            f"Unexpected device {bridge_rf_address} found, expected {entry.unique_id}"
        )
        _LOGGER.error(message)
        raise ConfigEntryNotReady(message)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    entry.runtime_data = coordinator

    # Always register a device for the bridge. It is necessary to set the
    # via_device attribute for the bound nodes.
    result = await api.bridge.node_product_name()
    if result is None or result.value is None:
        msg = "Node product name not available"
        raise ConfigEntryNotReady(msg)
    product_name = result.value

    result = await api.bridge.node_product_id()
    if result is None or result.value is None:
        msg = "Node product ID not available"
        raise ConfigEntryNotReady(msg)
    product_id = result.value

    result = await api.bridge.node_software_version()
    if result is None or result.value is None:
        msg = "Node software version not available"
        raise ConfigEntryNotReady(msg)
    sw_version = result.value

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(bridge_rf_address))},
        manufacturer=DEFAULT_NAME,
        name=product_name,
        model=product_name,
        model_id=f"0x{product_id:08X}",
        sw_version=f"0x{sw_version:04X}",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def update_listener(hass: HomeAssistant, entry: AiriosConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AiriosConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: AiriosDataUpdateCoordinator = entry.runtime_data
        coordinator.api.close()
    return unload_ok
