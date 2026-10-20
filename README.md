# Smarter Coffee for Home Assistant

Local control of the **Smarter Coffee 1st generation** (the one with "Smarter" printed on the panel) from Home Assistant. No cloud and no app needed: the integration talks to the machine directly on your network and gets status updates pushed from it.

Tested on firmware 22 with Home Assistant 2026.10.

## What you get

| Entity | Type | What it does |
| --- | --- | --- |
| State | sensor | Ready, grinding, brewing, keeping warm or not ready. Attribute `cups_brewed` counts up while brewing. |
| Water level | sensor | Empty, low, half or full. |
| Carafe | binary sensor | Carafe on the hotplate. |
| Not enough water | binary sensor | On when there is too little water to brew. |
| Brewing | binary sensor | On while grinding or brewing. |
| Cups | number | Cups, 1 to 12. Kept as the machine default, so it stays after a brew. |
| Keep warm | number | Hotplate time, 5 to 40 minutes. Stored on the machine, so its own buttons use it too. |
| Strength | select | Weak, medium or strong. Kept as the default. |
| Coffee | select | Beans (grind) or ground coffee in the filter. Kept as the default. |
| Hotplate | switch | Turn the hotplate on or off. |
| Require carafe | switch (config) | Refuse to brew without the carafe. |
| Single cup mode | switch (config) | Single cup instead of carafe mode. |
| Brew | button | Brew with what is selected right now. |
| Stop | button | Stop brewing. |

When the machine refuses a command, you get a readable error ("Put the carafe on the hotplate first", "Not enough water in the tank") instead of a silent failure.

### Brew action

`smarter_coffee.brew` brews with explicit settings. Anything you leave out is taken from what is selected on the machine.

```yaml
action: smarter_coffee.brew
target:
  entity_id: button.smarter_coffee_brew
data:
  cups: 4
  strength: strong
  keep_warm: 20
  grind: true
```

## Installation

1. In HACS, open the menu, choose **Custom repositories**, add `https://github.com/gtgaute/ha-smartercoffee` with type **Integration**.
2. Install **Smarter Coffee** and restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration > Smarter Coffee**. The machine is found automatically. If not, enter its IP address.

Home Assistant may also discover the machine by itself through DHCP.

Give the machine a fixed IP address in your router. The integration reconnects by itself if the connection drops.

## Getting the machine back on Wi-Fi without the app

The original app for the 1st generation is hard to find today. [`tools/smarter_wifi.py`](tools/smarter_wifi.py) does the same job:

1. Hold the top left (start) button until the display shows **WIFI reset** ("Reset" comes first, keep holding). Unplug the machine and plug it back in.
2. Connect your computer to the machine's own network, **Smarter Coffee:c1**.
3. Run `python3 tools/smarter_wifi.py`, pick your network and type the password.
4. The machine beeps when it has joined. Switch your computer back to your normal Wi-Fi.

The machine only supports 2.4 GHz and WPA2. Mesh systems that use one name for 2.4 and 5 GHz (such as Google Nest Wifi) work fine.

## Protocol notes

The machine runs an ESP8266 and listens on TCP and UDP port 2081. Each message is an id byte, an optional payload and the tail byte `0x7e`. [`protocol.py`](custom_components/smarter_coffee/protocol.py) documents every message the integration uses, and the tests use frames captured from a real machine.

## Credits

This integration stands on work by others:

- **[sergeymaysak/smartercoffee](https://github.com/sergeymaysak/smartercoffee)** by Sergiy Maysak (Apache 2.0). The original Home Assistant integration for this machine. Its protocol handling and choice of entities were the starting point for this one.
- **[iBrew](https://github.com/idserda/iBrew)** by Tristan (Tristan79) and contributors. The most complete description of the Smarter protocol, including the Wi-Fi setup commands used in `tools/smarter_wifi.py`.
- **[evilsocket](https://www.evilsocket.net/2016/10/09/IoCOFFEE-Reversing-the-Smarter-Coffee-IoT-machine-protocol-to-make-coffee-using-terminal/)** (Simone Margaritelli), who first reverse engineered the protocol in 2016.
- **[GarethWright/SmarterCoffeeWinApp](https://github.com/GarethWright/SmarterCoffeeWinApp)**, which confirmed the brew command layout.
- **[ian-kent/ikettle2](https://github.com/ian-kent/ikettle2)** and **[Jamstah/libsmarteram2](https://github.com/Jamstah/libsmarteram2)**, for cross checking the Wi-Fi commands.

The code is new and written for current Home Assistant (config flow, push updates, reconnect, translations, tests).

**Built with [Claude Code](https://claude.com/claude-code).** The protocol research, the integration, the tests and the Wi-Fi tool were made by Claude Code working together with the maintainer and tested against a real machine.

## Security

The machine accepts commands from anyone on your network, without a password. That is how the hardware works. Keep it on a network you trust.

## License

[Apache 2.0](LICENSE). See [NOTICE](NOTICE).
