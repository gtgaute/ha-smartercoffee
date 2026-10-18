"""Diagnostics for Smarter Coffee."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import SmarterCoffeeConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SmarterCoffeeConfigEntry
) -> dict[str, Any]:
    """Return the decoded and raw machine state."""
    client = entry.runtime_data
    status = client.status
    return {
        "connected": client.connected,
        "device_info": asdict(client.device_info) if client.device_info else None,
        "settings": asdict(client.settings) if client.settings else None,
        "carafe_required": client.carafe_required,
        "cup_mode": client.cup_mode,
        "status": {**asdict(status), "raw": status.raw.hex(" ")} if status else None,
    }
