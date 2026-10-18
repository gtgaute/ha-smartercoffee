"""Find Smarter Coffee machines on the local network."""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass

from homeassistant.components import network
from homeassistant.core import HomeAssistant

from .protocol import DEVICE_TYPE_COFFEE, PORT, TAIL, Command, Response

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DiscoveredMachine:
    """A machine that answered the broadcast."""

    host: str
    firmware: int


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.found: dict[str, DiscoveredMachine] = {}

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        # 65 <type> <firmware> 7e
        if (
            len(data) >= 4
            and data[0] == Response.DEVICE_INFO
            and data[3] == TAIL
            and data[1] == DEVICE_TYPE_COFFEE
        ):
            self.found[addr[0]] = DiscoveredMachine(addr[0], data[2])


async def async_discover(
    hass: HomeAssistant, timeout: float = 3.0
) -> list[DiscoveredMachine]:
    """Broadcast DEVICE_INFO and collect the answers."""
    targets = {"255.255.255.255"}
    targets.update(
        str(address) for address in await network.async_get_ipv4_broadcast_addresses(hass)
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    sock.bind(("", 0))
    transport, protocol = await asyncio.get_running_loop().create_datagram_endpoint(
        _DiscoveryProtocol, sock=sock
    )
    try:
        message = bytes((Command.DEVICE_INFO, TAIL))
        for _ in range(2):
            for target in targets:
                try:
                    transport.sendto(message, (target, PORT))
                except OSError as err:
                    _LOGGER.debug("Broadcast to %s failed: %s", target, err)
            await asyncio.sleep(timeout / 2)
    finally:
        transport.close()
    return list(protocol.found.values())


def mac_from_arp(host: str) -> str | None:
    """Look up a MAC address in the kernel ARP table (Linux only)."""
    try:
        with open("/proc/net/arp", encoding="ascii") as arp:
            next(arp)
            for line in arp:
                fields = line.split()
                if len(fields) >= 4 and fields[0] == host and fields[3] != "00:00:00:00:00:00":
                    return fields[3]
    except OSError:
        return None
    return None
