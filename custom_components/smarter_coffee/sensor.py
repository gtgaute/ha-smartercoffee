"""Sensors for Smarter Coffee."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmarterCoffeeConfigEntry
from .entity import SmarterCoffeeEntity
from .protocol import MachineState, WaterLevel


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmarterCoffeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    async_add_entities([StateSensor(entry), WaterLevelSensor(entry)])


class StateSensor(SmarterCoffeeEntity, SensorEntity):
    """What the machine is doing."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [state.value for state in MachineState]

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "state")

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        status = self.client.status
        return status.state.value if status else None

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        """Expose cups brewed so far while brewing."""
        status = self.client.status
        return {"cups_brewed": status.cups_brewed} if status else None


class WaterLevelSensor(SmarterCoffeeEntity, SensorEntity):
    """Water in the tank."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [level.name.lower() for level in WaterLevel]

    def __init__(self, entry: SmarterCoffeeConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "water_level")

    @property
    def native_value(self) -> str | None:
        """Return the level."""
        status = self.client.status
        return status.water_level.name.lower() if status else None
