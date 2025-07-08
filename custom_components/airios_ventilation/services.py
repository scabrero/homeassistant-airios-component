"""Services for the Airios integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.helpers.config_validation import make_entity_service_schema

ATTR_SUPPLY_FAN_SPEED = "supply_fan_speed"
ATTR_EXHAUST_FAN_SPEED = "exhaust_fan_speed"

SERVICE_SCHEMA_SET_PRESET_FAN_SPEED = make_entity_service_schema(
    {
        vol.Required(ATTR_SUPPLY_FAN_SPEED): vol.All(vol.Coerce(int)),
        vol.Required(ATTR_EXHAUST_FAN_SPEED): vol.All(vol.Coerce(int)),
    }
)

SERVICE_SET_PRESET_FAN_SPEED_AWAY = "set_preset_fan_speed_away"
SERVICE_SET_PRESET_FAN_SPEED_LOW = "set_preset_fan_speed_low"
SERVICE_SET_PRESET_FAN_SPEED_MEDIUM = "set_preset_fan_speed_medium"
SERVICE_SET_PRESET_FAN_SPEED_HIGH = "set_preset_fan_speed_high"
