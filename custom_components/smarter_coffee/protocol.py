"""Wire protocol for the Smarter Coffee machine (1st generation).

Every message is a message id, an optional payload and the tail byte 0x7E.
The machine listens on TCP 2081 and answers UDP discovery on the same port.

Sources: iBrew (Tristan79/idserda), sergeymaysak/smartercoffee and frames
captured from a machine running firmware 22.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

PORT = 2081
TAIL = 0x7E

DEVICE_TYPE_KETTLE = 0x01
DEVICE_TYPE_COFFEE = 0x02

CUPS_MIN = 1
CUPS_MAX = 12
KEEP_WARM_MIN = 5
KEEP_WARM_MAX = 40


class Command(IntEnum):
    """Messages sent to the machine."""

    BREW = 0x33
    STOP = 0x34
    SET_STRENGTH = 0x35
    SET_CUPS = 0x36
    BREW_DEFAULT = 0x37
    STORE_SETTINGS = 0x38
    TOGGLE_GRIND = 0x3C
    HOTPLATE_ON = 0x3E
    GET_SETTINGS = 0x48
    HOTPLATE_OFF = 0x4A
    SET_CARAFE_REQUIRED = 0x4B
    GET_CARAFE_REQUIRED = 0x4C
    SET_CUP_MODE = 0x4E
    GET_CUP_MODE = 0x4F
    DEVICE_INFO = 0x64


class Response(IntEnum):
    """Messages received from the machine."""

    COMMAND_STATUS = 0x03
    STATUS = 0x32
    SETTINGS = 0x49
    CARAFE_REQUIRED = 0x4D
    CUP_MODE = 0x50
    DEVICE_INFO = 0x65


# Total frame length (id + payload + tail) for responses with a fixed size.
# Fixed lengths let us split frames even if a payload byte happens to be 0x7E.
FRAME_LENGTHS: dict[int, int] = {
    Response.COMMAND_STATUS: 3,
    Response.STATUS: 7,
    Response.SETTINGS: 6,
    Response.CARAFE_REQUIRED: 3,
    Response.CUP_MODE: 3,
    Response.DEVICE_INFO: 4,
}


class Strength(IntEnum):
    """Coffee strength."""

    WEAK = 0
    MEDIUM = 1
    STRONG = 2


class WaterLevel(IntEnum):
    """Water level in the tank."""

    EMPTY = 0
    LOW = 1
    HALF = 2
    FULL = 3


class MachineState(StrEnum):
    """Combined machine state, most significant activity first."""

    GRINDING = "grinding"
    BREWING = "brewing"
    KEEPING_WARM = "keeping_warm"
    READY = "ready"
    NOT_READY = "not_ready"


class CommandResult(IntEnum):
    """Result codes in a COMMAND_STATUS response."""

    OK = 0x00
    ALREADY_BREWING = 0x01
    NO_CARAFE = 0x02
    NO_WATER = 0x03
    INVALID_VALUE = 0x04
    NO_CARAFE_ABORTED = 0x05
    NO_WATER_ABORTED = 0x06
    LOW_WATER_ABORTED = 0x07
    INVALID_TIMER = 0x0D
    WIFI_ERROR = 0x68
    INVALID_COMMAND = 0x69


@dataclass(frozen=True, slots=True)
class Status:
    """Decoded STATUS message (0x32)."""

    carafe_present: bool
    grind: bool
    ready: bool
    grinding: bool
    brewing: bool
    working: bool
    hotplate_on: bool
    timer_event: bool
    water_level: WaterLevel
    water_enough: bool
    strength: Strength
    cups: int
    cups_brewed: int
    raw: bytes

    @property
    def state(self) -> MachineState:
        """Return the single state shown to the user."""
        if self.grinding:
            return MachineState.GRINDING
        if self.brewing:
            return MachineState.BREWING
        if self.hotplate_on:
            return MachineState.KEEPING_WARM
        if self.ready:
            return MachineState.READY
        return MachineState.NOT_READY


@dataclass(frozen=True, slots=True)
class Settings:
    """Decoded SETTINGS message (0x49): the stored defaults."""

    cups: int
    strength: Strength
    grind: bool
    keep_warm: int


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Decoded DEVICE_INFO message (0x65)."""

    device_type: int
    firmware: int


def _bit(value: int, n: int) -> bool:
    return bool(value & (1 << n))


def _strength(value: int) -> Strength:
    try:
        return Strength(value)
    except ValueError:
        return Strength.STRONG


def parse_status(frame: bytes) -> Status:
    """Decode a STATUS frame: 32 <flags> <water> <unknown> <strength> <cups> 7e."""
    flags, water, _unknown, strength, cups = frame[1:6]
    return Status(
        carafe_present=_bit(flags, 0),
        grind=_bit(flags, 1),
        ready=_bit(flags, 2),
        grinding=_bit(flags, 3),
        brewing=_bit(flags, 4),
        working=_bit(flags, 5),
        hotplate_on=_bit(flags, 6),
        timer_event=_bit(flags, 7),
        water_level=WaterLevel(water & 0x03),
        water_enough=_bit(water, 4),
        strength=_strength(strength),
        cups=cups & 0x0F,
        cups_brewed=cups >> 4,
        raw=bytes(frame),
    )


def parse_settings(frame: bytes) -> Settings:
    """Decode a SETTINGS frame: 49 <cups> <strength> <grind> <keep warm> 7e."""
    cups, strength, grind, keep_warm = frame[1:5]
    return Settings(
        cups=cups,
        strength=_strength(strength),
        grind=bool(grind),
        keep_warm=keep_warm,
    )


def parse_device_info(frame: bytes) -> DeviceInfo:
    """Decode a DEVICE_INFO frame: 65 <type> <firmware> 7e."""
    return DeviceInfo(device_type=frame[1], firmware=frame[2])


def parse_carafe_required(frame: bytes) -> bool:
    """Decode CARAFE_REQUIRED (0x4D): 0 means the carafe is required."""
    return frame[1] == 0


def parse_cup_mode(frame: bytes) -> bool:
    """Decode CUP_MODE (0x50): 1 means single cup mode."""
    return frame[1] != 0


class FrameBuffer:
    """Split a TCP byte stream into frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Add received bytes and return all complete frames."""
        self._buffer.extend(data)
        frames: list[bytes] = []
        while self._buffer:
            length = FRAME_LENGTHS.get(self._buffer[0])
            if length is not None:
                if len(self._buffer) < length:
                    break
                if self._buffer[length - 1] == TAIL:
                    frames.append(bytes(self._buffer[:length]))
                    del self._buffer[:length]
                    continue
            # Unknown id or a frame that does not end where expected:
            # fall back to the next tail byte.
            end = self._buffer.find(TAIL)
            if end < 0:
                break
            frames.append(bytes(self._buffer[: end + 1]))
            del self._buffer[: end + 1]
        return frames


def _frame(*values: int) -> bytes:
    return bytes((*values, TAIL))


def encode_brew(cups: int, strength: Strength, keep_warm: int, grind: bool) -> bytes:
    """Brew with explicit settings. keep_warm is minutes, 0 for off."""
    return _frame(Command.BREW, cups, strength, keep_warm, int(grind))


def encode_set_cups(cups: int) -> bytes:
    """Select number of cups."""
    return _frame(Command.SET_CUPS, cups)


def encode_set_strength(strength: Strength) -> bytes:
    """Select strength."""
    return _frame(Command.SET_STRENGTH, strength)


def encode_hotplate_on(minutes: int) -> bytes:
    """Turn the hotplate on for a number of minutes."""
    return _frame(Command.HOTPLATE_ON, minutes)


def encode_set_carafe_required(required: bool) -> bytes:
    """Require (or not) the carafe to be on the base before brewing."""
    return _frame(Command.SET_CARAFE_REQUIRED, 0 if required else 1)


def encode_set_cup_mode(cup_mode: bool) -> bytes:
    """Select single cup mode or carafe mode."""
    return _frame(Command.SET_CUP_MODE, int(cup_mode))


def encode_store_settings(cups: int, strength: Strength, grind: bool, keep_warm: int) -> bytes:
    """Store new defaults. Note the order differs from the SETTINGS response."""
    return _frame(Command.STORE_SETTINGS, strength, cups, int(grind), keep_warm)


def encode_simple(command: Command) -> bytes:
    """Encode a command without payload."""
    return _frame(command)
