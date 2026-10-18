"""Binary sensors for Smarter Coffee."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmarterCoffeeConfigEntry
from .entity import SmarterCoffeeEntity
from .protocol import Status


@dataclass(frozen=True, kw_only=True)
class SmarterBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor."""

    value_fn: Callable[[Status], bool]


DESCRIPTIONS = (
    SmarterBinarySensorDescription(
        key="carafe",
        device_class=BinarySensorDeviceClass.PRESENCE,
        value_fn=lambda status: status.carafe_present,
    ),
    SmarterBinarySensorDescription(
        key="water_shortage",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda status: not status.water_enough,
    ),
    SmarterBinarySensorDescription(
        key="brewing",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda status: status.brewing or status.grinding,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmarterCoffeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    async_add_entities(SmarterBinarySensor(entry, d) for d in DESCRIPTIONS)


class SmarterBinarySensor(SmarterCoffeeEntity, BinarySensorEntity):
    """Binary sensor from the status flags."""

    entity_description: SmarterBinarySensorDescription

    def __init__(
        self, entry: SmarterCoffeeConfigEntry, description: SmarterBinarySensorDescription
    ) -> None:
        """Initialize."""
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the flag."""
        status = self.client.status
        return self.entity_description.value_fn(status) if status else None
