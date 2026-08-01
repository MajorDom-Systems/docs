# BLE (Bluetooth Low Energy) Discovery

## `BLEDiscoveryService`

Available as `self.dependencies.ble_discovery_service`.

The scanner runs persistently via Bleak's `BleakScanner`. You only need to register listeners; no explicit scanning calls are needed during normal operation.

### `register`

```python
def register(
    listener: BLEDiscoveryListener,
    service_ids: set[UUID],
) -> Callable[[], None]: ...
```

| Arg           | Type                   | Description                                                                                                   |
| ------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------- |
| `listener`    | `BLEDiscoveryListener` | Receives discovery events.                                                                                    |
| `service_ids` | `set[UUID]`            | BLE service UUIDs to filter on. Only advertisements containing at least one of these UUIDs trigger callbacks. |

Returns a cancel closure — call it in `stop()` to deregister.

______________________________________________________________________

## `BLEDiscoveryListener` (Protocol)

```python
class BLEDiscoveryListener(Protocol):
    async def ble_did_discover_device(self, ble: BLEDiscoveryService, info: BLEDiscoveryInfo): ...
    async def ble_did_update_device(self, ble: BLEDiscoveryService, info: BLEDiscoveryInfo): ...
    async def ble_did_remove_device(self, ble: BLEDiscoveryService, info: BLEDiscoveryInfo): ...
```

`ble_did_update_device` fires when the advertisement signature changes (local name, service UUIDs, manufacturer data, or service data). RSSI changes alone do not trigger updates.

`ble_did_remove_device` fires when no advertisement is received within the removal grace window (~11 s by default).

______________________________________________________________________

## `BLEDiscoveryInfo`

```python
@dataclass
class BLEDiscoveryInfo:
    device: BLEDevice
    advertisement: AdvertisementData
```

| Field           | Type                | Description                                                                            |
| --------------- | ------------------- | -------------------------------------------------------------------------------------- |
| `device`        | `BLEDevice`         | Bleak device object (`.address`, `.name`, `.details`)                                  |
| `advertisement` | `AdvertisementData` | Latest advertisement data (RSSI, manufacturer data, service data, service UUIDs, etc.) |

______________________________________________________________________

## Example

```python
_MY_SERVICE_UUIDS = {
    UUID("cba20d00-224d-11e6-9fb8-0002a5d5c51b"),
}

# in Controller
...
async def start(self):
    self._cancels: set[Callable[[], None]] = set()
    cancel = self.dependencies.ble_discovery_service.register(
        self,  # self implements BLEDiscoveryListener
        _MY_SERVICE_UUIDS,
    )
    self._cancels.add(cancel)

async def stop(self):
    for cancel in self._cancels:
        cancel()

# BLEDiscoveryListener Implementation

async def ble_did_discover_device(self, ble: BLEDiscoveryService, info: BLEDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.dependencies.output.controller_did_receive_discovery(self, discovery)

async def ble_did_update_device(self, ble: BLEDiscoveryService, info: BLEDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.dependencies.output.controller_did_update_discovery(self, discovery)

async def ble_did_remove_device(self, ble: BLEDiscoveryService, info: BLEDiscoveryInfo):
    discovery_id = self.device_uuid(info.device.address)
    if discovery_id in self._discoveries:
        self._discoveries.pop(discovery_id)
        await self.dependencies.output.controller_did_lose_discovery(self, discovery_id)
...
```
