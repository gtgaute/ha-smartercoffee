"""Buttons for Smarter Coffee."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmarterCoffeeConfigEntry
from .entity import SmarterCoffeeEntity
from .protocol import Strength


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmarterCoffeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    async_add_entities([BrewButton(entry), StopButton(entry)])


class BrewButton(SmarterCoffeeEntity, ButtonEntity):
    """Brew with what is selected now. Also target of the brew action."""

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "brew")

    async def async_press(self) -> None:
        """Brew with the current selection."""
        await self.async_brew()

    async def async_brew(
        self,
        cups: int | None = None,
        strength: str | None = None,
        keep_warm: int | None = None,
        grind: bool | None = None,
    ) -> None:
        """Brew, filling in anything not given from the machine."""
        status = self.client.status
        settings = self.client.settings
        assert status is not None and settings is not None
        await self._run(
            self.client.brew(
                cups=cups if cups is not None else status.cups,
                strength=Strength[strength.upper()] if strength else status.strength,
                keep_warm=keep_warm if keep_warm is not None else settings.keep_warm,
                grind=grind if grind is not None else status.grind,
            )
        )


class StopButton(SmarterCoffeeEntity, ButtonEntity):
    """Stop brewing."""

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "stop")

    async def async_press(self) -> None:
        """Stop."""
        await self._run(self.client.stop())
