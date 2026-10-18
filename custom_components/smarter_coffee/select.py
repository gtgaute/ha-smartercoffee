"""Selects for Smarter Coffee."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmarterCoffeeConfigEntry
from .entity import SmarterCoffeeEntity
from .protocol import Strength

MODE_BEANS = "beans"
MODE_FILTER = "filter"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmarterCoffeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    async_add_entities([StrengthSelect(entry), BrewModeSelect(entry)])


class StrengthSelect(SmarterCoffeeEntity, SelectEntity):
    """Coffee strength."""

    _attr_options = [s.name.lower() for s in Strength]

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "strength")

    @property
    def current_option(self) -> str | None:
        """Return strength."""
        status = self.client.status
        return status.strength.name.lower() if status else None

    async def async_select_option(self, option: str) -> None:
        """Select strength."""
        await self._run(self.client.set_strength(Strength[option.upper()]))


class BrewModeSelect(SmarterCoffeeEntity, SelectEntity):
    """Grind beans or use pre-ground coffee in the filter."""

    _attr_options = [MODE_BEANS, MODE_FILTER]

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "brew_mode")

    @property
    def current_option(self) -> str | None:
        """Return mode."""
        status = self.client.status
        if status is None:
            return None
        return MODE_BEANS if status.grind else MODE_FILTER

    async def async_select_option(self, option: str) -> None:
        """Select mode."""
        await self._run(self.client.set_grind(option == MODE_BEANS))
