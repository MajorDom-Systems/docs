# HomeKit

[`majordom-homekit`](https://github.com/MajorDom-Systems/integration-homekit) pairs HomeKit accessories with `aiohomekit`, which speaks HAP directly. Pairing needs the accessory's 8-digit setup code (`code`).

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `mdns/zeroconf` | yes | the runtime's DNS-SD; `aiohomekit` browses with its zeroconf instance (`self.peripherals.instance("mdns").async_zeroconf`) |

The controller brings no services or settings. IP accessories are found over mDNS and reached over the network. Bluetooth (HAP-BLE) accessories aren't wired yet.

- **OS / permissions:** mDNS on the LAN for discovery.
