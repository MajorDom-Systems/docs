# HomeKit

[`majordom-homekit`](https://github.com/MajorDom-Systems/integration-homekit) pairs HomeKit accessories with `aiohomekit`, which speaks HAP directly. Pairing needs the accessory's 8-digit setup code (`code`).

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `mdns/zeroconf` (`ZEROCONF`) | yes | the runtime's Zeroconf; `aiohomekit` browses `_hap._tcp` with its instance (`self.peripherals.instance(ZEROCONF).async_zeroconf`) |

The controller brings no services or settings. IP accessories are found over mDNS (`_hap._tcp` only) and reached over the network. Bluetooth (HAP-BLE) accessories aren't wired yet.

- **OS / permissions:** mDNS on the LAN for discovery.
