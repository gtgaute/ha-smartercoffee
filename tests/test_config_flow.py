"""Config flow tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.smarter_coffee.const import DOMAIN
from custom_components.smarter_coffee.discovery import DiscoveredMachine

from .conftest import FakeMachine, _client_on_port


@pytest.fixture
def fake_client(machine: FakeMachine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the flow and setup at the fake machine."""
    client = _client_on_port(machine.port)
    monkeypatch.setattr("custom_components.smarter_coffee.config_flow.SmarterCoffeeClient", client)
    monkeypatch.setattr("custom_components.smarter_coffee.SmarterCoffeeClient", client)
    monkeypatch.setattr(
        "custom_components.smarter_coffee.config_flow.mac_from_arp", lambda host: None
    )


async def test_user_discovered(hass: HomeAssistant, fake_client: None) -> None:
    """A machine found by broadcast can be picked."""
    with patch(
        "custom_components.smarter_coffee.config_flow.async_discover",
        return_value=[DiscoveredMachine("127.0.0.1", 22)],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["step_id"] == "pick"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "127.0.0.1"


async def test_user_manual_error_then_ok(hass: HomeAssistant, fake_client: None) -> None:
    """Without discovery the user types an address."""
    with patch(
        "custom_components.smarter_coffee.config_flow.async_discover", return_value=[]
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "unreachable"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_dhcp(hass: HomeAssistant, fake_client: None) -> None:
    """DHCP discovery asks for confirmation and uses the MAC as id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(ip="127.0.0.1", hostname="esp_000001", macaddress="5ccf7f000001"),
    )
    assert result["step_id"] == "discovery_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "5c:cf:7f:00:00:01"
