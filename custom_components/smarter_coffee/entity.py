"""Base entity for Smarter Coffee."""

from __future__ import annotations

from collections.abc import Awaitable

from homeassistant.const import CONF_MAC
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity

from . import SmarterCoffeeConfigEntry
from .client import SmarterCoffeeCommandError, SmarterCoffeeError
from .const import DOMAIN, MANUFACTURER, MODEL


class SmarterCoffeeEntity(Entity):
    """Entity backed by the pushed machine state."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: SmarterCoffeeConfigEntry, key: str) -> None:
        """Initialize."""
        self.client = entry.runtime_data
        assert entry.unique_id is not None
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_translation_key = key
        info = self.client.device_info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            connections=(
                {(CONNECTION_NETWORK_MAC, entry.data[CONF_MAC])}
                if entry.data.get(CONF_MAC)
                else set()
            ),
            manufacturer=MANUFACTURER,
            model=MODEL,
            name="Smarter Coffee",
            sw_version=str(info.firmware) if info else None,
        )

    @property
    def available(self) -> bool:
        """Available while connected and the first status has arrived."""
        return self.client.connected and self.client.status is not None

    async def async_added_to_hass(self) -> None:
        """Follow pushed updates."""
        self.async_on_remove(self.client.add_listener(self.async_write_ha_state))

    async def _run(self, action: Awaitable[None]) -> None:
        """Run a command and turn failures into readable errors."""
        try:
            await action
        except SmarterCoffeeCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=f"command_{err.reason}"
            ) from err
        except SmarterCoffeeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_connected"
            ) from err
