"""Coordinator for the Airios integration."""

from __future__ import annotations

import datetime
import logging
import typing

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyairios.data_model import AiriosData
from pyairios.exceptions import AiriosException

from .const import DEFAULT_NAME

if typing.TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pyairios import Airios

_LOGGER = logging.getLogger(__name__)


class AiriosDataUpdateCoordinator(DataUpdateCoordinator[AiriosData]):
    """The Airios data update coordinator."""

    fetch_result_status: bool

    def __init__(
        self,
        hass: HomeAssistant,
        api: Airios,
        update_interval: int,
        *,
        fetch_result_status: bool,
    ) -> None:
        """Initialize the Airios data coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DEFAULT_NAME} DataUpdateCoordinator",
            update_interval=datetime.timedelta(seconds=update_interval),
        )
        self.api = api
        self.fetch_result_status = fetch_result_status

    async def _async_update_data(self) -> AiriosData:
        """Fetch state by polling API and forward it to Home Assistant."""
        _LOGGER.debug("Updating HA data state cache")
        try:
            return await self.api.fetch(with_status=self.fetch_result_status)
        except AiriosException as err:
            msg = "Error during state cache update"
            raise UpdateFailed(msg) from err
