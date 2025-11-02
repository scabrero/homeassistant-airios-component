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
from pyairios import Airios
from pyairios.client import (
    AiriosBaseTransport,
    AiriosRtuTransport,
    AiriosTcpTransport,
)
from pyairios.properties import AiriosDeviceProperty

from .const import (
    CONF_FETCH_RESULT_STATUS,
    DEFAULT_FETCH_RESULT_STATUS,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    BridgeType,
)
from .coordinator import AiriosDataUpdateCoordinator
from .services import async_setup_services

if typing.TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType
    from pyairios.constants import ProductId
    from pyairios.data_model import AiriosDeviceData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type AiriosConfigEntry = ConfigEntry[AiriosDataUpdateCoordinator]


async def async_setup(
    hass: HomeAssistant,
    config: ConfigType,  # noqa: ARG001 # pylint: disable=unused-argument
) -> bool:
    """Set up integration services."""
    async_setup_services(hass)
    return True


def _get_transport(entry: AiriosConfigEntry) -> AiriosBaseTransport:
    transport: AiriosBaseTransport | None = None
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
    return transport


def _get_bridge_data(data: AiriosDeviceData) -> tuple[int, ProductId, str, int]:
    if AiriosDeviceProperty.RF_ADDRESS not in data:
        msg = "Failed to get bridge RF address"
        raise ConfigEntryNotReady(msg)
    bridge_rf_address = data[AiriosDeviceProperty.RF_ADDRESS].value

    if AiriosDeviceProperty.PRODUCT_ID not in data:
        msg = "Failed to get bridge product ID"
        raise ConfigEntryNotReady(msg)
    product_id = data[AiriosDeviceProperty.PRODUCT_ID].value

    if AiriosDeviceProperty.PRODUCT_NAME not in data:
        msg = "Failed to get bridge product name"
        raise ConfigEntryNotReady(msg)
    product_name = data[AiriosDeviceProperty.PRODUCT_NAME].value

    if AiriosDeviceProperty.SOFTWARE_VERSION not in data:
        msg = "Failed to get bridge software version"
        raise ConfigEntryNotReady(msg)
    sw_version = data[AiriosDeviceProperty.SOFTWARE_VERSION].value

    return (bridge_rf_address, product_id, product_name, sw_version)


async def async_setup_entry(hass: HomeAssistant, entry: AiriosConfigEntry) -> bool:
    """Set up Airios from a config entry."""
    transport = _get_transport(entry)
    modbus_address = entry.data[CONF_ADDRESS]
    api = Airios(transport, modbus_address)

    coordinator = AiriosDataUpdateCoordinator(
        hass,
        api,
        update_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        fetch_result_status=entry.options.get(
            CONF_FETCH_RESULT_STATUS, DEFAULT_FETCH_RESULT_STATUS
        ),
    )
    await coordinator.async_config_entry_first_refresh()

    (rf_address, product_id, product_name, sw_version) = _get_bridge_data(
        coordinator.data.nodes[coordinator.data.bridge_key]
    )

    if entry.unique_id != str(rf_address):
        message = f"Unexpected device {rf_address} found, expected {entry.unique_id}"
        _LOGGER.error(message)
        raise ConfigEntryNotReady(message)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    entry.runtime_data = coordinator

    # Always register a device for the bridge. It is necessary to set the
    # via_device attribute for the bound nodes.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(rf_address))},
        manufacturer=DEFAULT_NAME,
        name=product_name,
        model=product_name,
        model_id=f"0x{product_id:08X}",
        sw_version=f"0x{sw_version:04X}",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # sets up Airios fans, sensors etc.
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
