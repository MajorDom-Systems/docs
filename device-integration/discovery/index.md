# Discovery Services

Discovery services are injected into every controller via `self.dependencies`. They abstract transport-level device advertisement into a unified listener pattern, so your integration never needs to manage its own mDNS, SSDP, or BLE scanner.

Three services are available:

| Service                    | Protocol                     | Dependency field                               |
| -------------------------- | ---------------------------- | ---------------------------------------------- |
| `ZeroconfDiscoveryService` | mDNS / DNS-SD                | `self.dependencies.zeroconf_discovery_service` |
| `SSDPDiscoveryService`     | UPnP SSDP                    | `self.dependencies.ssdp_discovery_service`     |
| `BLEDiscoveryService`      | Bluetooth Low Energy (Bleak) | `self.dependencies.ble_discovery_service`      |

## Common Pattern

All three services share the same usage contract:

- Call `register(...)` to subscribe. It returns a **cancel closure**.
- Store the cancel closure and call it in your controller's `stop()`.
- The services are already started and stopped by the Hub — do not call `start()` or `stop()` on them yourself.

______________________________________________________________________

## Combining Multiple Discovery Services

A controller can register with multiple discovery protocols simultaneously, or with a few service types using the same protocol. Usage doesn't change.

```python
async def start(self):
    self._cancels: set[Callable[[], None]] = set()
    self._cancels.add(self.dependencies.zeroconf_discovery_service.register(
        self, {"_myprotocol._tcp.local."}
    ))
    self._cancels.add(self.dependencies.ble_discovery_service.register(
        self, {MY_SERVICE_UUID}
    ))

async def stop(self):
    for cancel in self._cancels:
        cancel()
```
