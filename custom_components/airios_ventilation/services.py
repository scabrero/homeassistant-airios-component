"""Services for the Airios integration."""

from __future__ import annotations

import typing

import voluptuous as vol
from homeassistant.components.fan import ATTR_PRESET_MODE
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.config_validation import make_entity_service_schema
from pyairios.constants import ResetMode

from .const import DOMAIN

if typing.TYPE_CHECKING:
    from pyairios.models.brdg_02r13 import BRDG02R13

    from .coordinator import AiriosDataUpdateCoordinator

ATTR_SUPPLY_FAN_SPEED = "supply_fan_speed"
ATTR_EXHAUST_FAN_SPEED = "exhaust_fan_speed"
ATTR_PRESET_OVERRIDE_TIME = "preset_override_time"

SERVICE_SCHEMA_SET_PRESET_FAN_SPEED = make_entity_service_schema(
    {
        vol.Required(ATTR_SUPPLY_FAN_SPEED): vol.All(vol.Coerce(int)),
        vol.Required(ATTR_EXHAUST_FAN_SPEED): vol.All(vol.Coerce(int)),
    }
)

SERVICE_SCHEMA_SET_PRESET_MODE_DURATION = make_entity_service_schema(
    {
        vol.Required(ATTR_PRESET_MODE): vol.In(["low", "medium", "high"]),
        vol.Required(ATTR_PRESET_OVERRIDE_TIME): vol.All(vol.Coerce(int)),
    }
)

SERVICE_SET_PRESET_FAN_SPEED_AWAY = "set_preset_fan_speed_away"
SERVICE_SET_PRESET_FAN_SPEED_LOW = "set_preset_fan_speed_low"
SERVICE_SET_PRESET_FAN_SPEED_MEDIUM = "set_preset_fan_speed_medium"
SERVICE_SET_PRESET_FAN_SPEED_HIGH = "set_preset_fan_speed_high"
SERVICE_SET_PRESET_MODE_DURATION = "set_preset_mode_duration"
SERVICE_FILTER_RESET = "filter_reset"
SERVICE_DEVICE_RESET = "device_reset"
SERVICE_FACTORY_RESET = "factory_reset"


async def _get_api_device(service_call: ServiceCall) -> BRDG02R13:
    service_data = service_call.data
    device_registry = dr.async_get(service_call.hass)
    if not (device := device_registry.async_get(service_data[ATTR_DEVICE_ID])):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_device_entry",
            translation_placeholders={"service_name": "device_reset"},
        )

    config_entry = None
    for entry_id in device.config_entries:
        config_entry = service_call.hass.config_entries.async_get_entry(entry_id)
        if config_entry is not None and config_entry.domain == DOMAIN:
            break

    if (
        config_entry is None
        or device is None
        or config_entry.state != ConfigEntryState.LOADED
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_config_entry",
            translation_placeholders={"service_name": "device_reset"},
        )

    rf_address = None
    for dev_id in (
        device.identifiers if isinstance(device, dr.DeviceEntry) else {device}
    ):
        if dev_id[0] == DOMAIN:
            rf_address = int(dev_id[1])

    if not rf_address:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_device_entry",
            translation_placeholders={"service_name": "device_reset"},
        )

    coordinator: AiriosDataUpdateCoordinator = config_entry.runtime_data
    bridge = coordinator.api.bridge
    if (result := await bridge.device_rf_address()) and result.value != rf_address:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_bridge_rf_address",
            translation_placeholders={
                "service_name": "device_reset",
                "rf_address": f"0x{rf_address:06X}",
            },
        )
    return coordinator.api.bridge


async def handle_device_reset_call(service_call: ServiceCall) -> None:
    """Handle device reset call."""
    bridge = await _get_api_device(service_call)
    await bridge.reset(ResetMode.SOFT_RESET)


async def handle_factory_reset_call(service_call: ServiceCall) -> None:
    """Handle device reset call."""
    bridge = await _get_api_device(service_call)
    await bridge.reset(ResetMode.FACTORY_RESET)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register services for Airios integration."""
    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_DEVICE_RESET,
        schema=vol.Schema(
            {
                vol.Required(ATTR_DEVICE_ID): str,
            },
        ),
        service_func=handle_device_reset_call,
    )
    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_FACTORY_RESET,
        schema=vol.Schema(
            {
                vol.Required(ATTR_DEVICE_ID): str,
            },
        ),
        service_func=handle_factory_reset_call,
    )
