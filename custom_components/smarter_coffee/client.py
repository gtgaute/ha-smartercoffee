"""Async client for the Smarter Coffee machine.

Keeps one TCP connection open. The machine pushes a STATUS frame whenever
something changes; commands are answered with COMMAND_STATUS (and a data
frame for queries).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from collections.abc import Callable

from .protocol import (
    DEVICE_TYPE_COFFEE,
    PORT,
    Command,
    CommandResult,
    DeviceInfo,
    FrameBuffer,
    Response,
    Settings,
    Status,
    Strength,
    encode_brew,
    encode_hotplate_on,
    encode_set_carafe_required,
    encode_set_cup_mode,
    encode_set_cups,
    encode_set_strength,
    encode_simple,
    encode_store_settings,
    parse_carafe_required,
    parse_cup_mode,
    parse_device_info,
    parse_settings,
    parse_status,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
REQUEST_TIMEOUT = 5
# The machine is quiet while idle. Ping it so a dead link is noticed.
IDLE_PING_INTERVAL = 60
RECONNECT_MIN = 5
RECONNECT_MAX = 120


class SmarterCoffeeError(Exception):
    """Base error."""


class SmarterCoffeeConnectionError(SmarterCoffeeError):
    """Machine could not be reached."""


class SmarterCoffeeCommandError(SmarterCoffeeError):
    """Machine rejected a command."""

    def __init__(self, result: int) -> None:
        """Store the result code."""
        self.result = result
        try:
            name = CommandResult(result).name.lower()
        except ValueError:
            name = f"unknown_0x{result:02x}"
        self.reason = name
        super().__init__(f"Command rejected: {name}")


class _Request:
    """A command waiting for its response frames."""

    def __init__(self, expect: tuple[int, ...]) -> None:
        self.waiting = set(expect)
        self.frames: dict[int, bytes] = {}
        self.future: asyncio.Future[dict[int, bytes]] = (
            asyncio.get_running_loop().create_future()
        )

    def offer(self, frame: bytes) -> bool:
        """Take the frame if it belongs to this request."""
        if frame[0] not in self.waiting:
            return False
        self.waiting.discard(frame[0])
        self.frames[frame[0]] = frame
        if not self.waiting and not self.future.done():
            self.future.set_result(self.frames)
        return True


class SmarterCoffeeClient:
    """Connection to one machine."""

    def __init__(self, host: str, port: int = PORT) -> None:
        """Initialize."""
        self.host = host
        self.port = port
        self.status: Status | None = None
        self.settings: Settings | None = None
        self.device_info: DeviceInfo | None = None
        self.carafe_required: bool | None = None
        self.cup_mode: bool | None = None

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._request: _Request | None = None
        self._listeners: list[Callable[[], None]] = []
        self._closing = False

    @property
    def connected(self) -> bool:
        """Return True while the TCP connection is up."""
        return self._writer is not None and not self._writer.is_closing()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call listener on every state change. Returns a remove function."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def connect(self) -> None:
        """Connect and load the current state. Raises on failure."""
        self._closing = False
        await self._open()
        try:
            await self.refresh()
        except SmarterCoffeeError:
            await self._close_transport()
            raise

    async def refresh(self) -> None:
        """Query device info, defaults, carafe and cup mode."""
        frames = await self._request_frames(
            encode_simple(Command.DEVICE_INFO), (Response.DEVICE_INFO,)
        )
        self.device_info = parse_device_info(frames[Response.DEVICE_INFO])
        if self.device_info.device_type != DEVICE_TYPE_COFFEE:
            raise SmarterCoffeeConnectionError(
                f"Device at {self.host} is not a coffee machine"
            )
        frames = await self._request_frames(
            encode_simple(Command.GET_SETTINGS),
            (Response.SETTINGS, Response.COMMAND_STATUS),
        )
        self.settings = parse_settings(frames[Response.SETTINGS])
        frames = await self._request_frames(
            encode_simple(Command.GET_CARAFE_REQUIRED),
            (Response.CARAFE_REQUIRED, Response.COMMAND_STATUS),
        )
        self.carafe_required = parse_carafe_required(frames[Response.CARAFE_REQUIRED])
        frames = await self._request_frames(
            encode_simple(Command.GET_CUP_MODE),
            (Response.CUP_MODE, Response.COMMAND_STATUS),
        )
        self.cup_mode = parse_cup_mode(frames[Response.CUP_MODE])
        self._notify()

    async def disconnect(self) -> None:
        """Close for good (no reconnect)."""
        self._closing = True
        if self._reconnect_task:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
            self._reconnect_task = None
        await self._close_transport()

    async def _open(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
            )
        except (OSError, TimeoutError) as err:
            raise SmarterCoffeeConnectionError(
                f"Could not connect to {self.host}:{self.port}: {err}"
            ) from err
        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self._read_task = asyncio.create_task(
            self._read_loop(self._reader), name=f"smarter_coffee {self.host}"
        )
        _LOGGER.debug("Connected to %s", self.host)

    async def _close_transport(self) -> None:
        task, self._read_task = self._read_task, None
        writer, self._writer = self._writer, None
        self._reader = None
        if task and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if writer:
            writer.close()
            with contextlib.suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 2)
        if self._request and not self._request.future.done():
            self._request.future.set_exception(
                SmarterCoffeeConnectionError("Connection closed")
            )

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        buffer = FrameBuffer()
        try:
            while True:
                try:
                    data = await asyncio.wait_for(reader.read(256), IDLE_PING_INTERVAL)
                except TimeoutError:
                    if self._ping_task is None or self._ping_task.done():
                        self._ping_task = asyncio.create_task(self._ping())
                    continue
                if not data:
                    raise ConnectionResetError("Closed by machine")
                for frame in buffer.feed(data):
                    self._handle_frame(frame)
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError) as err:
            _LOGGER.debug("Connection to %s lost: %s", self.host, err)
        await self._close_transport()
        self._notify()
        if not self._closing:
            self._reconnect_task = asyncio.create_task(self._reconnect())

    async def _ping(self) -> None:
        try:
            await self._request_frames(
                encode_simple(Command.DEVICE_INFO), (Response.DEVICE_INFO,)
            )
        except SmarterCoffeeError:
            # Closing the writer ends the read loop, which reconnects.
            if self._writer:
                self._writer.close()

    async def _reconnect(self) -> None:
        delay = RECONNECT_MIN
        while not self._closing:
            await asyncio.sleep(delay)
            try:
                await self.connect()
            except SmarterCoffeeError as err:
                _LOGGER.debug("Reconnect to %s failed: %s", self.host, err)
                delay = min(delay * 2, RECONNECT_MAX)
            else:
                _LOGGER.info("Reconnected to Smarter Coffee at %s", self.host)
                return

    def _handle_frame(self, frame: bytes) -> None:
        if self._request and self._request.offer(frame):
            return
        match frame[0]:
            case Response.STATUS if len(frame) == 7:
                status = parse_status(frame)
                if status != self.status:
                    self.status = status
                    self._notify()
            case Response.SETTINGS if len(frame) == 6:
                self.settings = parse_settings(frame)
                self._notify()
            case Response.COMMAND_STATUS:
                pass
            case _:
                _LOGGER.debug("Unhandled frame from %s: %s", self.host, frame.hex(" "))

    async def _request_frames(
        self, payload: bytes, expect: tuple[int, ...]
    ) -> dict[int, bytes]:
        async with self._lock:
            if not self.connected or self._writer is None:
                raise SmarterCoffeeConnectionError("Not connected")
            request = _Request(expect)
            self._request = request
            try:
                self._writer.write(payload)
                await self._writer.drain()
                return await asyncio.wait_for(request.future, REQUEST_TIMEOUT)
            except TimeoutError as err:
                raise SmarterCoffeeConnectionError(
                    f"No answer to {payload.hex(' ')}"
                ) from err
            except OSError as err:
                raise SmarterCoffeeConnectionError(str(err)) from err
            finally:
                self._request = None

    async def _command(self, payload: bytes) -> None:
        frames = await self._request_frames(payload, (Response.COMMAND_STATUS,))
        result = frames[Response.COMMAND_STATUS][1]
        if result != CommandResult.OK:
            raise SmarterCoffeeCommandError(result)

    async def brew(
        self, cups: int, strength: Strength, keep_warm: int, grind: bool
    ) -> None:
        """Start brewing with explicit settings."""
        await self._command(encode_brew(cups, strength, keep_warm, grind))

    async def stop(self) -> None:
        """Stop brewing."""
        await self._command(encode_simple(Command.STOP))

    async def set_cups(self, cups: int) -> None:
        """Select number of cups."""
        await self._command(encode_set_cups(cups))

    async def set_strength(self, strength: Strength) -> None:
        """Select strength."""
        await self._command(encode_set_strength(strength))

    async def set_grind(self, grind: bool) -> None:
        """Select beans (grind) or filter. The machine only offers a toggle."""
        if self.status is None or self.status.grind != grind:
            await self._command(encode_simple(Command.TOGGLE_GRIND))

    async def hotplate_on(self, minutes: int) -> None:
        """Turn the hotplate on."""
        await self._command(encode_hotplate_on(minutes))

    async def hotplate_off(self) -> None:
        """Turn the hotplate off."""
        await self._command(encode_simple(Command.HOTPLATE_OFF))

    async def set_carafe_required(self, required: bool) -> None:
        """Require the carafe before brewing."""
        await self._command(encode_set_carafe_required(required))
        self.carafe_required = required
        self._notify()

    async def set_cup_mode(self, cup_mode: bool) -> None:
        """Select single cup mode."""
        await self._command(encode_set_cup_mode(cup_mode))
        self.cup_mode = cup_mode
        self._notify()

    async def store_settings(
        self, cups: int, strength: Strength, grind: bool, keep_warm: int
    ) -> None:
        """Store new defaults on the machine."""
        await self._command(encode_store_settings(cups, strength, grind, keep_warm))
        self.settings = Settings(cups, strength, grind, keep_warm)
        self._notify()
