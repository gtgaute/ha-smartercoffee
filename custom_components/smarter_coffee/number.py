"""Numbers for Smarter Coffee."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmarterCoffeeConfigEntry
from .entity import SmarterCoffeeEntity
from .protocol import CUPS_MAX, CUPS_MIN, KEEP_WARM_MAX, KEEP_WARM_MIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmarterCoffeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up numbers."""
    async_add_entities([CupsNumber(entry), KeepWarmNumber(entry)])


class CupsNumber(SmarterCoffeeEntity, NumberEntity):
    """Number of cups selected on the machine."""

    _attr_native_min_value = CUPS_MIN
    _attr_native_max_value = CUPS_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "cups")

    @property
    def native_value(self) -> int | None:
        """Return cups."""
        status = self.client.status
        return status.cups if status else None

    async def async_set_native_value(self, value: float) -> None:
        """Select cups."""
        await self._run(self.client.set_cups(int(value)))


class KeepWarmNumber(SmarterCoffeeEntity, NumberEntity):
    """Hotplate time. Stored as the machine default, so the buttons on the machine use it too."""

    _attr_native_min_value = KEEP_WARM_MIN
    _attr_native_max_value = KEEP_WARM_MAX
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "keep_warm")

    @property
    def native_value(self) -> int | None:
        """Return minutes."""
        settings = self.client.settings
        return settings.keep_warm if settings else None

    async def async_set_native_value(self, value: float) -> None:
        """Store new default hotplate time."""
        settings = self.client.settings
        assert settings is not None
        await self._run(
            self.client.store_settings(
                settings.cups, settings.strength, settings.grind, int(value)
            )
        )
