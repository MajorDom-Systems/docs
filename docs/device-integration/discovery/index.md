# Discovery Services

Discovery services are peripherals the runtime runs in the Hub's process. Your controller needs them like any radio or server, and the bound one arrives as `self.peripherals.instance(<family>)`. They abstract transport-level device advertisement into a unified listener pattern, so your integration never needs to manage its own mDNS, SSDP, or BLE scanner.

Three are available:

| Capability | Need | Contract | Protocol |
|---|---|---|---|
| `mdns/zeroconf` | `Need("mdns", ["zeroconf"])` | [`Zeroconf`](zeroconf.md) | mDNS / DNS-SD |
| `upnp/ssdp` | `Need("upnp", ["ssdp"])` | [`SSDP`](ssdp.md) | UPnP SSDP |
| `ble/router` | `Need("ble", ["router"])` | [`BLERouter`](ble.md) | Bluetooth Low Energy, through every radio the hub has |

The contracts (interfaces and info types only) live in [`majordom_integration_sdk.capabilities`](https://github.com/MajorDom-Systems/integration-sdk/tree/master/majordom_integration_sdk/capabilities); the implementations in the SDK runtime, see [The SDK Runtime](../../hub/radios.md#in-process-providers).

## Common Pattern

All three services share the same usage contract:

- Call `register(...)` to subscribe. It returns a **cancel closure**.
- Store the cancel closure and call it in your controller's `stop()`.
- The runtime starts and stops them — do not call `start()` or `stop()` on them yourself.
- Declare the need `required=False` when the integration works without it: a hub without Bluetooth then still runs it, with `instance("ble")` returning `None`.


---

## Combining Multiple Discovery Services

A controller can register with multiple discovery protocols simultaneously, or with a few service types using the same protocol. Usage doesn't change.

```python
needs = [Need("mdns", ["zeroconf"]), Need("ble", ["router"])]

async def start(self):
    self._cancels: set[Callable[[], None]] = set()
    self._cancels.add(self.peripherals.instance("mdns").register(
        self, {"_myprotocol._tcp.local."}
    ))
    self._cancels.add(self.peripherals.instance("ble").register(
        self, {MY_SERVICE_UUID}
    ))

async def stop(self):
    for cancel in self._cancels:
        cancel()
```
