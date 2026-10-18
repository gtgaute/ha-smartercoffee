"""Protocol tests with frames from a real machine."""

from custom_components.smarter_coffee.protocol import (
    FrameBuffer,
    MachineState,
    Strength,
    WaterLevel,
    encode_brew,
    encode_store_settings,
    parse_settings,
    parse_status,
)

from .conftest import OK, SETTINGS, STATUS_BREWING, STATUS_READY


def test_parse_ready_status() -> None:
    """32 07 13 00 01 02: carafe on, beans, ready, full tank, medium, 2 cups."""
    status = parse_status(STATUS_READY)
    assert status.carafe_present
    assert status.grind
    assert status.ready
    assert not status.brewing
    assert status.water_level is WaterLevel.FULL
    assert status.water_enough
    assert status.strength is Strength.MEDIUM
    assert status.cups == 2
    assert status.state is MachineState.READY


def test_parse_brewing_status() -> None:
    """Heater bit set and cups brewed in the high nibble."""
    status = parse_status(STATUS_BREWING)
    assert status.state is MachineState.BREWING
    assert status.cups == 4
    assert status.cups_brewed == 2


def test_parse_settings() -> None:
    """49 02 01 01 28: 2 cups, medium, beans, 40 minutes."""
    settings = parse_settings(SETTINGS)
    assert (settings.cups, settings.strength, settings.grind, settings.keep_warm) == (
        2,
        Strength.MEDIUM,
        True,
        40,
    )


def test_frame_buffer_splits_and_waits() -> None:
    """Frames are split by length, partial frames wait for more data."""
    buffer = FrameBuffer()
    stream = SETTINGS + OK + STATUS_READY
    assert buffer.feed(stream[:8]) == [SETTINGS]
    assert buffer.feed(stream[8:]) == [OK, STATUS_READY]


def test_frame_buffer_tail_inside_payload() -> None:
    """A fixed size frame survives a 0x7e payload byte."""
    frame = bytes.fromhex("32 07 13 7e 01 02 7e")
    assert FrameBuffer().feed(frame) == [frame]


def test_encode() -> None:
    """Brew and store use different argument orders."""
    assert encode_brew(4, Strength.STRONG, 10, True) == bytes.fromhex("33 04 02 0a 01 7e")
    assert encode_store_settings(4, Strength.STRONG, True, 10) == bytes.fromhex(
        "38 02 04 01 0a 7e"
    )
