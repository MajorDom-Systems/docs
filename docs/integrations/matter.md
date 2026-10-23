# Matter

[`majordom-matter`](https://github.com/MajorDom-Systems/integration-matter) drives a matter-server over its WebSocket API. The server owns the Matter fabric and commissioning; it has no radio of its own.

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `matter/matter-server` | yes | the `matterjs-server` service below; standalone, any matter-server you run. The URL is the server's base (`ws://127.0.0.1:5580`): the integration connects to `/ws` and serves `/ble` |
| `ble/router` | no | the Hub's [Bluetooth router](../device-integration/discovery/ble.md), which the controller lends matterjs-server in `router` mode |
| `ip` (for `matterjs-server`) | yes | the host |
| `thread/otbr-rest` (for `matterjs-server`) | no | a Thread border router: the `otbr` or `silabs-multiprotocol` service on a Thread-capable stick. Without one, Matter works over Wi-Fi and Ethernet |
| `ble/bluez` (for `matterjs-server`) | no | a host adapter [reserved](../hub/radios.md#reservations) for matterjs-server, in `direct` mode; otherwise the router holds every adapter and this stays unbound |

- **Services it brings:** `matterjs-server`, which the Hub runs while Matter is in use. Thread is an optional need of the service, so a border router runs whenever a stick can serve one.
- **Settings:** *Bluetooth* (`ble_mode`): `router` (the default) or `direct`, see [below](#bluetooth).
- **Context:** the Hub's Wi-Fi (`context.wifi`) and Thread network (`context.thread_dataset`), handed to matterjs-server so new devices join them.
- **OS / permissions:** Bluetooth for commissioning: the Hub's, through BlueZ (D-Bus), in `router` mode; only matterjs-server's in `direct` mode. mDNS on the LAN for on-network discovery.

## Bluetooth

The setting `ble_mode` picks who drives the Bluetooth radio while commissioning.

### `router` (the default)

matterjs-server runs with `BLE_PROXY=true`. The integration's Bluetooth delegate (`MatterServerBLEDelegate`, `ble_delegate.py`) lends it the Hub's router (every local adapter and ESPHome Bluetooth proxy) over matterjs-server's BLE proxy protocol, on `/ble` of the `matter/matter-server` URL. The controller lists the commissionable devices the router hears (service `0xFFF6`) as discoveries. See [Bluetooth](../hub/radios.md#bluetooth).

### `direct`

matterjs-server drives an adapter of its own, which the user reserves for it:

```
PUT /v1/api/hardware/reservations/matterjs-server/ble
{"url": "hci1"}
```

The runtime binds that adapter to matterjs-server's optional `ble/bluez` need, ahead of the router. Its compose gets `BLUETOOTH_ADAPTER` (the adapter's `index`) and `BLE_PROXY` off (`{peripherals.ble.url:!true}` renders empty once an adapter is bound). `BLUETOOTH_ADAPTER` follows matterjs-server's `--bluetooth-adapter` flag; its README documents only the flag, so the environment name is unverified.

matterjs-server's API can commission over Bluetooth (`commission_with_code`) but can't list commissionable Bluetooth devices: `discover_commissionable_nodes` is mDNS only. So in this mode the controller lists no Bluetooth devices. It offers one discovery, "Matter device (enter its pairing code)", which takes a manual pairing code or the QR. matterjs-server then finds the device over Bluetooth by the code's discriminator and commissions it. The discovery is offered again after each pairing, so more devices can be added the same way. On-network (mDNS) discovery is the same in both modes.

Use it where the Hub process has no usable Bluetooth or D-Bus. The case it was made for: the CI hardware runner, a de-rooted (userns-remapped) container, where D-Bus SASL EXTERNAL rejects the remapped uid, so the Hub's adapters can't reach `bluetoothd`. Passing Bluetooth into that container would need `userns=host` (real root) and re-privilege the runner. In `direct` mode only matterjs-server, which already runs with `userns_mode: host`, touches the radio, so the runner stays de-rooted.

A permanent "enter code" discovery stands in for a dedicated "add a Matter device by code" action, which would be the nicer flow.

## Standalone

`run_controller(MatterController)` runs matterjs-server in Docker, as the Hub does. Without Docker, run a matter-server yourself and pin its base URL: `run_controller(MatterController, docker=False, pinned={"matter": Endpoint("matter", "matter-server", "ws://localhost:5580")})`, or `pin matter ws://localhost:5580` in the CLI. Thread devices also need an OpenThread Border Router. See [Standalone Mode](../device-integration/standalone.md#connecting-to-radios-and-services).

For the code behind this, see [Connecting to Radios and Services](../device-integration/radios.md#matter-with-its-own-service).
