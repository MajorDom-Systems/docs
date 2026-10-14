# HomeKit

[`majordom-homekit`](https://github.com/MajorDom-Systems/integration-homekit) pairs HomeKit accessories with `aiohomekit`, which speaks HAP directly. Pairing needs the accessory's 8-digit setup code (`code`).

## Needs

None: the controller declares no needs, services or settings. IP accessories are found over mDNS and reached over the network.

- **OS / permissions:** mDNS on the LAN for discovery.
