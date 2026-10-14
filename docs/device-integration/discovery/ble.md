# Bluetooth

## `BLEService`

Available as `self.dependencies.ble_discovery_service`.

One service hears every Bluetooth radio the hub has and reaches every device through them:

- each local adapter (`hci0`, a USB dongle as `hci1`, …);
- ESPHome devices with [`bluetooth_proxy`](https://esphome.io/components/bluetooth_proxy/), added by the ESPHome integration while they are connected.

From this release `BLEService` is the only supported way for an integration to use Bluetooth. Don't open adapters or scan with `bleak` directly: it competes with the hub's own radios and bypasses the proxies.

Your integration registers what it wants to hear about and connects by address. It never knows which radio heard the device or carries the connection. You make no scanning calls: sources listen continuously, and a source that hears nothing for a minute is restarted (its radio went away, e.g. `bluetoothd` restarted).

`BLEDiscoveryService` is the previous name, kept as an alias for one release.

### `register`

```python
def register(
    listener: BLEDiscoveryListener,
    matchers: Iterable[BLEMatcher | UUID],
) -> Callable[[], None]: ...
```

| Arg | Type | Description |
|---|---|---|
| `listener` | `BLEDiscoveryListener` | Receives discovery events. |
| `matchers` | `Iterable[BLEMatcher \| UUID]` | Devices matching any of them trigger callbacks. A `UUID` matches that service. |

Returns a cancel closure. Call it in `stop()` to deregister. Devices heard before you registered are reported to you as discovered.

### `connect`

```python
async def connect(address: str, on_disconnect: Callable[[], None] = ...) -> BLEConnection: ...
```

Opens a GATT connection through the source hearing the device best (strongest signal), falling back to the others. Raises `ConnectionError` when none can connect. `on_disconnect` is called when the connection drops.

### `exclusive`

```python
async with ble.exclusive(address, owner="myintegration") as lease:
    connection = await lease.connect(on_lost)
    ...  # pair, commission, update firmware
```

Leases the source hearing the device best to you, e.g. while pairing it. That source stops scanning until the block ends, and `connect` calls of others avoid it; every other source keeps working. `lease.connect(on_disconnect)` connects through exactly the leased source (`lease.source`, e.g. `hci0` or `esphome:<mac>`).

A source someone else holds is waited for `wait` seconds (default 1), then the next best is tried, round after round. After `timeout` seconds (default 30) it raises `BLEBusyError`, a `ConnectionError`. Leaving the block releases the source and resumes scanning on it. Disconnect before you leave.

### `devices`

Every device heard recently, as the source hearing it best sees it.

---

## `BLEMatcher`

```python
@dataclass(frozen=True)
class BLEMatcher:
    service_uuid: UUID | None = None          # advertised as a service or in the service data
    manufacturer_id: int | None = None
    manufacturer_data_start: bytes = b""
    local_name_prefix: str | None = None
```

Every field that is set must match. Examples:

| Devices | Matcher |
|---|---|
| Matter, commissionable | `BLEMatcher(service_uuid=UUID("0000fff6-0000-1000-8000-00805f9b34fb"))` |
| HomeKit accessories | `BLEMatcher(manufacturer_id=0x004C, manufacturer_data_start=b"\x06")` |
| ESPHome Improv | `BLEMatcher(service_uuid=UUID("00467768-6228-2272-4663-277478268000"))` |

---

## `BLEDiscoveryListener` (Protocol)

```python
class BLEDiscoveryListener(Protocol):
    async def ble_did_discover_device(self, ble: BLEService, info: BLEDiscoveryInfo): ...
    async def ble_did_update_device(self, ble: BLEService, info: BLEDiscoveryInfo): ...
    async def ble_did_remove_device(self, ble: BLEService, info: BLEDiscoveryInfo): ...
```

`ble_did_update_device` fires when the advertisement changes (local name, service UUIDs, manufacturer data, or service data). RSSI changes alone, and other sources hearing the same device, do not trigger updates.

`ble_did_remove_device` fires when no source has heard the device within the removal grace window (~11 s).

## `BLEDiscoveryInfo`

```python
@dataclass
class BLEDiscoveryInfo:
    device: BLEDevice
    advertisement: AdvertisementData
    source: str = "local"
```

| Field | Type | Description |
|---|---|---|
| `device` | `BLEDevice` | Bleak device object (`.address`, `.name`) |
| `advertisement` | `AdvertisementData` | Latest advertisement from the source hearing it best (RSSI, manufacturer data, service data, service UUIDs, …) |
| `source` | `str` | That source: `hci0`, `esphome:<mac>`, … |

!!! warning "Don't build IDs from the address"
    Many devices rotate their Bluetooth address, and each source may report a different one. Derive discovery IDs from the advertisement's content: a serial number, a MAC address inside the manufacturer data, Matter's discriminator with the vendor and product IDs.

---

## `BLEConnection`

Characteristics are addressed by handle, as every source (BlueZ, an ESPHome proxy) knows them.

```python
class BLEConnection(Protocol):
    mtu: int
    async def services(self) -> list[GattService]: ...       # each with its characteristics, uuid + handle + properties
    async def read(self, handle: int) -> bytes: ...
    async def write(self, handle: int, data: bytes, response: bool = True) -> None: ...
    async def start_notify(self, handle: int, callback: Callable[[bytes], None]) -> None: ...  # notifications and indications
    async def stop_notify(self, handle: int) -> None: ...
    async def disconnect(self) -> None: ...
```

---

## Sources

A source is anything that hears advertisements and can connect: `BLESource` with `name`, `start(on_advertisement)`, `stop()` and `connect(address, on_disconnect)`. Add one while the service runs with `await ble.add_source(source)`, and remove it with `await ble.remove_source(name)`.

`BLEService()` uses every local adapter. `BLEService(sources=[...])` uses only the sources you give it. In tests, use `FakeBLESource` from `majordom_integration_sdk.testing`:

```python
radio = FakeBLESource("hci0", connection=my_fake_connection)
ble = BLEService(sources=[radio])
await ble.start()
radio.advertise("AA:BB:CC:DD:EE:FF", service_data={"0000fff6-0000-1000-8000-00805f9b34fb": payload})
```

---

## Example

```python
_SWITCHBOT = [BLEMatcher(service_uuid=UUID("cba20d00-224d-11e6-9fb8-0002a5d5c51b"))]

# in Controller
...
async def start(self):
    self._ble_cancel = self.dependencies.ble_discovery_service.register(self, _SWITCHBOT)

async def stop(self):
    self._ble_cancel()

# BLEDiscoveryListener Implementation

async def ble_did_discover_device(self, ble: BLEService, info: BLEDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.dependencies.output.controller_did_receive_discovery(self, discovery)

async def ble_did_update_device(self, ble: BLEService, info: BLEDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.dependencies.output.controller_did_update_discovery(self, discovery)

async def ble_did_remove_device(self, ble: BLEService, info: BLEDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        if self._discoveries.pop(discovery.id, None):
            await self.dependencies.output.controller_did_lose_discovery(self, discovery.id)

async def _read_battery(self, address: str) -> int:
    connection = await self.dependencies.ble_discovery_service.connect(address)
    try:
        services = await connection.services()
        battery = next(c for s in services for c in s.characteristics if c.uuid.startswith("00002a19"))
        return (await connection.read(battery.handle))[0]
    finally:
        await connection.disconnect()
...
```
