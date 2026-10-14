# ESPHome

[`majordom-esphome`](https://github.com/MajorDom-Systems/integration-esphome) speaks directly to ESPHome devices over the network.

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `thread/otbr-rest` | no | a Thread border router: the `otbr` or `multiprotocol` service on a Thread-capable stick. Only devices on Thread need it; Wi-Fi and Ethernet devices need nothing |

- **Services it brings:** none.
- **Settings:** *Bluetooth proxies*, on by default. ESPHome devices with `bluetooth_proxy` lend their Bluetooth radio to the Hub while they are connected. A device serves one Hub at a time: turn the setting off only if another Hub needs a device's Bluetooth proxy.
- **OS / permissions:** network access to the ESPHome devices (same LAN or routable subnet); mDNS or SSDP for discovery, depending on configuration.

For the code behind this, see [Connecting to Radios and Services](../device-integration/radios.md#esphome-an-optional-border-router).
