"""Constants for the Airios integration."""

from enum import IntEnum, auto

from pyairios import ProductId


class BridgeType(IntEnum):
    """Type of RF bridge."""

    SERIAL = auto()
    NETWORK = auto()


DOMAIN = "airios_ventilation"
DEFAULT_NAME = "Airios"
DEFAULT_SCAN_INTERVAL = 30

CONF_BRIDGE_RF_ADDRESS = "bridge_rf_address"
CONF_RF_ADDRESS = "rf_address"
CONF_DEFAULT_TYPE = BridgeType.SERIAL
CONF_DEFAULT_HOST = "192.168.1.254"
CONF_DEFAULT_PORT = 502
CONF_DEFAULT_SERIAL_MODBUS_ADDRESS = 207

# The Ethernet RF bridge uses address 1, but this device is not
# yet supported by pyairios library. Use the serial device address
# in case a Modbus RTU - TCP gateway is used.
CONF_DEFAULT_NETWORK_MODBUS_ADDRESS = 207


# TODO fetch these from api for easy maintenance, not const > move to configflow.init.api
SUPPORTED_UNITS: dict[str, ProductId] = {
    "Siber DF Optima 2": ProductId.VMD_02RPS78,
    "Siber DF EVO": ProductId.VMD_02RPS78,
    "ClimaRad Ventura V1": ProductId.VMD_07RPS13,
}
# TODO fetch these from api for easy maintenance, not const > move to configflow.init.api
SUPPORTED_ACCESSORIES: dict[str, ProductId] = {
    "Siber 4 button remote": ProductId.VMN_05LM02,
}
