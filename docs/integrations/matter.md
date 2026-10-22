# Matter

[`majordom-matter`](https://github.com/MajorDom-Systems/integration-matter) drives a matter-server over its WebSocket API. The server owns the Matter fabric and commissioning; it has no radio of its own.

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `matter/matter-server-ws` | yes | the `matterjs-server` service below; standalone, any matter-server you run |
| `ble/matter-ble-proxy` | no | the `matterjs-server` service's BLE proxy, which the controller serves from the Hub's `BLEService` |
| `ip` (for `matterjs-server`) | yes | the host |
| `thread/otbr-rest` (for `matterjs-server`) | no | a Thread border router: the `otbr` or `silabs-multiprotocol` service on a Thread-capable stick. Without one, Matter works over Wi-Fi and Ethernet |

- **Services it brings:** `matterjs-server`, which the Hub runs while Matter is in use. Thread is an optional need of the service, so a border router runs whenever a stick can serve one.
- **Settings:** none.
- **Context:** the Hub's Wi-Fi (`context.wifi`) and Thread network (`context.thread_dataset`), handed to matterjs-server so new devices join them.
- **OS / permissions:** BLE access (D-Bus) for commissioning; mDNS on the LAN for on-network discovery.

## Bluetooth

matterjs-server runs with `BLE_PROXY=true`. The integration's Bluetooth delegate (`MatterServerBLEDelegate`, `ble_delegate.py`) serves it the Hub's `BLEService` (every local adapter and ESPHome Bluetooth proxy) over matterjs-server's BLE proxy protocol, the `ble/matter-ble-proxy` endpoint on `/ble`. See [Bluetooth](../hub/radios.md#bluetooth).

## Standalone

Pass the server as `links={"matter": Endpoint("matter", "matter-server-ws", "ws://localhost:5580/ws")}`. Thread devices also need an OpenThread Border Router. See [Standalone Mode](../device-integration/standalone.md#connecting-to-radios-and-services).

For the code behind this, see [Connecting to Radios and Services](../device-integration/radios.md#matter-with-its-own-service).
