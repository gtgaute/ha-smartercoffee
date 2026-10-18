"""Integration tests against the fake machine."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import STATUS_BREWING, FakeMachine


async def test_entities(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """State is read from the machine on setup."""
    assert setup_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.smarter_coffee_state").state == "ready"
    assert hass.states.get("sensor.smarter_coffee_water_level").state == "full"
    assert hass.states.get("binary_sensor.smarter_coffee_carafe").state == "on"
    assert hass.states.get("binary_sensor.smarter_coffee_not_enough_water").state == "off"
    assert hass.states.get("number.smarter_coffee_cups").state == "2"
    assert hass.states.get("number.smarter_coffee_keep_warm").state == "40"
    assert hass.states.get("select.smarter_coffee_strength").state == "medium"
    assert hass.states.get("select.smarter_coffee_coffee").state == "beans"
    assert hass.states.get("switch.smarter_coffee_require_carafe").state == "on"
    assert hass.states.get("switch.smarter_coffee_single_cup_mode").state == "off"


async def test_push_update(
    hass: HomeAssistant, setup_entry: MockConfigEntry, machine: FakeMachine
) -> None:
    """A pushed status frame updates entities."""
    machine.push(STATUS_BREWING)
    await hass.async_block_till_done(wait_background_tasks=True)
    for _ in range(20):
        if hass.states.get("sensor.smarter_coffee_state").state == "brewing":
            break
        await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get("sensor.smarter_coffee_state")
    assert state.state == "brewing"
    assert state.attributes["cups_brewed"] == 2
    assert hass.states.get("binary_sensor.smarter_coffee_brewing").state == "on"


async def test_brew_button(
    hass: HomeAssistant, setup_entry: MockConfigEntry, machine: FakeMachine
) -> None:
    """The button brews with the current selection and stored keep warm time."""
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.smarter_coffee_brew"}, blocking=True
    )
    assert machine.received[-1] == bytes.fromhex("33 02 01 28 01 7e")


async def test_brew_action(
    hass: HomeAssistant, setup_entry: MockConfigEntry, machine: FakeMachine
) -> None:
    """The brew action overrides selected values."""
    await hass.services.async_call(
        "smarter_coffee",
        "brew",
        {"entity_id": "button.smarter_coffee_brew", "cups": 6, "strength": "strong", "keep_warm": 0},
        blocking=True,
    )
    assert machine.received[-1] == bytes.fromhex("33 06 02 00 01 7e")


async def test_brew_error(
    hass: HomeAssistant, setup_entry: MockConfigEntry, machine: FakeMachine
) -> None:
    """A rejected command becomes a readable error."""
    machine.next_result = 0x02
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.smarter_coffee_brew"}, blocking=True
        )
    assert err.value.translation_key == "command_no_carafe"


async def test_settings(
    hass: HomeAssistant, setup_entry: MockConfigEntry, machine: FakeMachine
) -> None:
    """Selects, numbers and switches send the right frames."""
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.smarter_coffee_cups", "value": 5}, blocking=True
    )
    assert machine.received[-1] == bytes.fromhex("36 05 7e")
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.smarter_coffee_strength", "option": "weak"}, blocking=True,
    )
    assert machine.received[-1] == bytes.fromhex("35 00 7e")
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.smarter_coffee_coffee", "option": "filter"}, blocking=True,
    )
    assert machine.received[-1] == bytes.fromhex("3c 7e")
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.smarter_coffee_keep_warm", "value": 15}, blocking=True,
    )
    assert machine.received[-1] == bytes.fromhex("38 01 02 01 0f 7e")
    assert hass.states.get("number.smarter_coffee_keep_warm").state == "15"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.smarter_coffee_hotplate"}, blocking=True
    )
    assert machine.received[-1] == bytes.fromhex("3e 0f 7e")
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.smarter_coffee_require_carafe"}, blocking=True
    )
    assert machine.received[-1] == bytes.fromhex("4b 01 7e")
    assert hass.states.get("switch.smarter_coffee_require_carafe").state == "off"


async def test_unavailable_when_machine_goes_away(
    hass: HomeAssistant, setup_entry: MockConfigEntry, machine: FakeMachine
) -> None:
    """Entities go unavailable when the connection drops."""
    await machine.stop()
    for _ in range(20):
        await hass.async_block_till_done(wait_background_tasks=False)
        if hass.states.get("sensor.smarter_coffee_state").state == "unavailable":
            break
    assert hass.states.get("sensor.smarter_coffee_state").state == "unavailable"
    await hass.config_entries.async_unload(setup_entry.entry_id)
