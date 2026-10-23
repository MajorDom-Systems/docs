# ESPHome

[`majordom-esphome`](https://github.com/MajorDom-Systems/integration-esphome) speaks directly to ESPHome devices over the network.

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `mdns/dns-sd` | yes | the runtime's DNS-SD: nodes are found over mDNS |
| `thread/otbr-rest` | no | a Thread border router: the `otbr` or `silabs-multiprotocol` service on a Thread-capable stick. Only devices on Thread need it; Wi-Fi and Ethernet devices need nothing |
| `ble/router` | no | the Hub's [Bluetooth router](../device-integration/discovery/ble.md): it sets unprovisioned nodes up over Improv BLE |

- **Offers:** each connected node with `bluetooth_proxy` as `ble/esphome-proxy`, its Bluetooth source as the endpoint's `instance`, through `self.platform.offers`. The router hears through it, and tries a proxy that reports no connection slot free (`free_slots`) last. A leased proxy pauses scanning and stays subscribed. See [Offering endpoints](../device-integration/radios.md#offering-endpoints).

- **Services it brings:** none.
- **Settings:** *Bluetooth proxies*, on by default. ESPHome devices with `bluetooth_proxy` lend their Bluetooth radio to the Hub while they are connected. A device serves one Hub at a time: turn the setting off only if another Hub needs a device's Bluetooth proxy.
- **OS / permissions:** network access to the ESPHome devices (same LAN or routable subnet); mDNS for discovery.

For the code behind this, see [Connecting to Radios and Services](../device-integration/radios.md#esphome-an-optional-border-router-and-offers).
