"""The Smarter Coffee integration."""

from __future__ import annotations

import probatio
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import ConfigType

from .client import SmarterCoffeeClient, SmarterCoffeeError
from .const import (
    ATTR_CUPS,
    ATTR_GRIND,
    ATTR_KEEP_WARM,
    ATTR_STRENGTH,
    DOMAIN,
    SERVICE_BREW,
)
from .protocol import CUPS_MAX, CUPS_MIN, KEEP_WARM_MAX, Strength

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type SmarterCoffeeConfigEntry = ConfigEntry[SmarterCoffeeClient]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the brew action."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_BREW,
        entity_domain=BUTTON_DOMAIN,
        schema={
            probatio.Optional(ATTR_CUPS): probatio.All(
                probatio.Coerce(int), probatio.Range(CUPS_MIN, CUPS_MAX)
            ),
            probatio.Optional(ATTR_STRENGTH): probatio.In(
                [s.name.lower() for s in Strength]
            ),
            probatio.Optional(ATTR_KEEP_WARM): probatio.All(
                probatio.Coerce(int), probatio.Range(0, KEEP_WARM_MAX)
            ),
            probatio.Optional(ATTR_GRIND): cv.boolean,
        },
        func="async_brew",
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SmarterCoffeeConfigEntry) -> bool:
    """Connect to the machine and set up entities."""
    client = SmarterCoffeeClient(entry.data[CONF_HOST])
    try:
        await client.connect()
    except SmarterCoffeeError as err:
        await client.disconnect()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": entry.data[CONF_HOST]},
        ) from err
    entry.runtime_data = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmarterCoffeeConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.disconnect()
    return unloaded
