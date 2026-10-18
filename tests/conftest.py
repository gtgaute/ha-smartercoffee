"""Fixtures: a fake Smarter Coffee machine on localhost."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smarter_coffee.const import DOMAIN

# Frames captured from a real machine (firmware 22).
STATUS_READY = bytes.fromhex("32 07 13 00 01 02 7e")
STATUS_BREWING = bytes.fromhex("32 17 13 00 01 24 7e")
SETTINGS = bytes.fromhex("49 02 01 01 28 7e")
OK = bytes.fromhex("03 00 7e")


class FakeMachine:
    """Answers like the real machine and records what it was sent."""

    def __init__(self) -> None:
        self.received: list[bytes] = []
        self.next_result = 0x00
        self.writers: list[asyncio.StreamWriter] = []
        self.server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for writer in self.writers:
            writer.close()
        assert self.server
        self.server.close()
        await self.server.wait_closed()

    def push(self, frame: bytes) -> None:
        for writer in self.writers:
            writer.write(frame)

    async def _client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.writers.append(writer)
        writer.write(STATUS_READY)
        try:
            while data := await reader.read(64):
                self.received.append(data)
                writer.write(self._answer(data))
                await writer.drain()
        except ConnectionError:
            pass
        finally:
            self.writers.remove(writer)

    def _answer(self, data: bytes) -> bytes:
        match data[0]:
            case 0x64:
                return bytes.fromhex("65 02 16 7e") + STATUS_READY
            case 0x48:
                return SETTINGS + OK
            case 0x4C:
                return bytes.fromhex("4d 00 7e") + OK
            case 0x4F:
                return bytes.fromhex("50 00 7e") + OK
            case _:
                return bytes((0x03, self.next_result, 0x7E))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components."""


@pytest.fixture
async def machine(socket_enabled: None) -> AsyncGenerator[FakeMachine]:
    """Run a fake machine."""
    fake = FakeMachine()
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, machine: FakeMachine, monkeypatch: pytest.MonkeyPatch
) -> MockConfigEntry:
    """Set up the integration against the fake machine."""
    monkeypatch.setattr("custom_components.smarter_coffee.client.PORT", machine.port)
    monkeypatch.setattr(
        "custom_components.smarter_coffee.SmarterCoffeeClient",
        _client_on_port(machine.port),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="5c:cf:7f:00:00:01",
        data={CONF_HOST: "127.0.0.1", CONF_MAC: "5c:cf:7f:00:00:01"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _client_on_port(port: int) -> type:
    from custom_components.smarter_coffee.client import SmarterCoffeeClient

    class _Client(SmarterCoffeeClient):
        def __init__(self, host: str) -> None:
            # "unreachable" stands in for a wrong address: a closed local port.
            if host == "unreachable":
                super().__init__("127.0.0.1", 1)
            else:
                super().__init__(host, port)

    return _Client
