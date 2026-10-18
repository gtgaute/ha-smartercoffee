"""Switches for Smarter Coffee."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmarterCoffeeConfigEntry
from .const import DEFAULT_KEEP_WARM
from .entity import SmarterCoffeeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmarterCoffeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    async_add_entities(
        [HotplateSwitch(entry), CarafeRequiredSwitch(entry), CupModeSwitch(entry)]
    )


class HotplateSwitch(SmarterCoffeeEntity, SwitchEntity):
    """Hotplate under the carafe."""

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "hotplate")

    @property
    def is_on(self) -> bool | None:
        """Return True while heating."""
        status = self.client.status
        return status.hotplate_on if status else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Heat for the stored keep warm time."""
        settings = self.client.settings
        minutes = settings.keep_warm if settings and settings.keep_warm else DEFAULT_KEEP_WARM
        await self._run(self.client.hotplate_on(minutes))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop heating."""
        await self._run(self.client.hotplate_off())


class CarafeRequiredSwitch(SmarterCoffeeEntity, SwitchEntity):
    """Refuse to brew without the carafe on the base."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "carafe_required")

    @property
    def is_on(self) -> bool | None:
        """Return the setting."""
        return self.client.carafe_required

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Require the carafe."""
        await self._run(self.client.set_carafe_required(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Allow brewing without the carafe."""
        await self._run(self.client.set_carafe_required(False))


class CupModeSwitch(SmarterCoffeeEntity, SwitchEntity):
    """Single cup mode instead of carafe mode."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "cup_mode")

    @property
    def is_on(self) -> bool | None:
        """Return the setting."""
        return self.client.cup_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Use single cup mode."""
        await self._run(self.client.set_cup_mode(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Use carafe mode."""
        await self._run(self.client.set_cup_mode(False))
