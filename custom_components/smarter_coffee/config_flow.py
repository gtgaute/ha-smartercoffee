"""Config flow for Smarter Coffee."""

from __future__ import annotations

import logging
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .client import SmarterCoffeeClient, SmarterCoffeeError
from .const import DOMAIN
from .discovery import async_discover, mac_from_arp

_LOGGER = logging.getLogger(__name__)

MANUAL = "manual"


class SmarterCoffeeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._host: str | None = None
        self._mac: str | None = None
        self._firmware: int | None = None
        self._discovered: dict[str, int] = {}

    async def _async_probe(self, host: str) -> str | None:
        """Connect once. Return an error key or None."""
        client = SmarterCoffeeClient(host)
        try:
            await client.connect()
        except SmarterCoffeeError as err:
            _LOGGER.debug("Probe of %s failed: %s", host, err)
            return "cannot_connect"
        finally:
            await client.disconnect()
        assert client.device_info is not None
        self._firmware = client.device_info.firmware
        if self._mac is None:
            mac = await self.hass.async_add_executor_job(mac_from_arp, host)
            self._mac = format_mac(mac) if mac else None
        return None

    async def _async_set_identity(self, host: str) -> None:
        await self.async_set_unique_id(self._mac or host)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

    def _create(self, host: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title="Smarter Coffee", data={CONF_HOST: host, CONF_MAC: self._mac}
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Look for machines, then let the user pick one or type an address."""
        configured = {entry.data[CONF_HOST] for entry in self._async_current_entries()}
        found = await async_discover(self.hass)
        self._discovered = {m.host: m.firmware for m in found if m.host not in configured}
        if not self._discovered:
            return await self.async_step_manual()
        return await self.async_step_pick()

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a discovered machine."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            if host == MANUAL:
                return await self.async_step_manual()
            if (error := await self._async_probe(host)) is None:
                await self._async_set_identity(host)
                return self._create(host)
            errors["base"] = error
        options = [
            SelectOptionDict(value=host, label=f"{host} (firmware {fw})")
            for host, fw in self._discovered.items()
        ]
        options.append(SelectOptionDict(value=MANUAL, label=MANUAL))
        return self.async_show_form(
            step_id="pick",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_HOST): SelectSelector(
                        SelectSelectorConfig(options=options, translation_key="pick")
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter an address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if (error := await self._async_probe(host)) is None:
                await self._async_set_identity(host)
                return self._create(host)
            errors["base"] = error
        return self.async_show_form(
            step_id="manual",
            data_schema=probatio.Schema({probatio.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """A device with an Espressif MAC asked for an address."""
        self._mac = format_mac(discovery_info.macaddress)
        await self.async_set_unique_id(self._mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        self._async_abort_entries_match({CONF_HOST: discovery_info.ip})
        if await self._async_probe(discovery_info.ip) is not None:
            return self.async_abort(reason="not_smarter_coffee")
        self._host = discovery_info.ip
        self.context["title_placeholders"] = {"host": self._host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered machine."""
        assert self._host is not None
        if user_input is not None:
            return self._create(self._host)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"host": self._host, "firmware": str(self._firmware)},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            self._mac = entry.data.get(CONF_MAC)
            if (error := await self._async_probe(host)) is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema({probatio.Required(CONF_HOST): str}), entry.data
            ),
            errors=errors,
        )
