# Discovery Services

Discovery services tell your controller when devices appear, change or go away, over mDNS, SSDP or Bluetooth. Need them by the SDK's typed needs (`majordom_integration_sdk.capabilities`) and read the bound one with `self.peripherals.instance(ZEROCONF)`. They share one listener pattern, and your integration never runs its own mDNS, SSDP or BLE scanner.

Three are available:

| Capability | Need | Contract | Protocol |
|---|---|---|---|
| `mdns/zeroconf` | `ZEROCONF` | [`Zeroconf`](zeroconf.md) | mDNS / DNS-SD |
| `upnp/ssdp` | `UPNP_SSDP` | [`SSDP`](ssdp.md) | UPnP SSDP |
| `ble/router` | `BLE_ROUTER` | [`BLERouter`](ble.md) | Bluetooth Low Energy, through every radio the hub has; for everything else over BLE see [Bluetooth LE](../capabilities/ble.md) |

The contracts (interfaces and info types only) live in [`majordom_integration_sdk.capabilities`](https://github.com/MajorDom-Systems/integration-sdk/tree/develop/majordom_integration_sdk/capabilities). See [Peripherals](../peripherals.md) for needs in general.

## Common Pattern

All three services share the same usage contract:

- Call `register(...)` to subscribe. It returns a **cancel closure**.
- Store the cancel closure and call it in your controller's `stop()`.
- The runtime starts and stops them — do not call `start()` or `stop()` on them yourself.
- Make the need optional, `BLE_ROUTER(is_required=False)`, when the integration works without it: a hub without Bluetooth then still runs it, with `instance(BLE_ROUTER)` returning `None`.


---

## Combining Multiple Discovery Services

A controller can register with multiple discovery protocols simultaneously, or with a few service types using the same protocol. Usage doesn't change.

```python
from majordom_integration_sdk.capabilities import BLE_ROUTER, ZEROCONF

needs = [ZEROCONF, BLE_ROUTER]

async def start(self):
    self._cancels: set[Callable[[], None]] = set()
    self._cancels.add(self.peripherals.instance(ZEROCONF).register(
        self, {"_myprotocol._tcp.local."}
    ))
    self._cancels.add(self.peripherals.instance(BLE_ROUTER).register(
        self, {MY_SERVICE_UUID}
    ))

async def stop(self):
    for cancel in self._cancels:
        cancel()
```
