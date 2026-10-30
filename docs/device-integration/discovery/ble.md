# Bluetooth

## `BLERouter`

The `ble/router` peripheral. Declare `BLE_ROUTER` (`dataclasses.replace(BLE_ROUTER, is_required=False)` when the integration works without Bluetooth), and the router arrives as `self.peripherals.instance(BLE_ROUTER)`. Its contract is `majordom_integration_sdk.capabilities.BLERouter`; the runtime's implementation is `BLEService` (provider `ble-router`, the SDK's `ble` extra).

One router hears every Bluetooth radio the hub has and reaches every device through them. Its sources are the raw Bluetooth endpoints the runtime binds to it:

| Capability | Source |
|---|---|
| `ble/bluez` | each host adapter (`hci0`, a USB dongle as `hci1`, …), offered one by one, through bleak (BlueZ on Linux) |
| `ble/silabs-cpc-hci` | the Bluetooth of a Silicon Labs multi-PAN radio, when its firmware has it (see [Multi-PAN radio images](../../hub/radio-images.md#bluetooth-over-cpc)) |
| `ble/esphome-proxy` | each ESPHome node with [`bluetooth_proxy`](https://esphome.io/components/bluetooth_proxy/), a [`BLEProxy`](../radios.md#bringing-peripherals-along) the ESPHome integration brings along while it is connected (`esphome/<bt-mac>`) |

The router needs `Need("ble", ["bluez", "silabs-cpc-hci", "esphome-proxy"], is_many=True, is_required=False)`, and the runtime binds its providers before any integration, so it takes every raw adapter. The router is the only supported way for an integration to use Bluetooth. Don't need `ble/bluez`, open adapters or scan with `bleak` directly: such a need stays unbound, with the reason and the fix (`every provider taken by ble-router — use Need("ble", ["router"])`), and a direct scan competes with the hub's own radios and bypasses the proxies. The one exception is Matter's [direct mode](../../integrations/matter.md#bluetooth), with the router disabled. (`ble/majordom` is kept for a future MajorDom Bluetooth chip.)

Your integration registers what it wants to hear about and connects by address. It never knows which radio heard the device or carries the connection. You make no scanning calls: sources listen continuously, and a source that hears nothing for a minute is restarted (its radio went away, e.g. `bluetoothd` restarted).

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

Opens a GATT connection through the source hearing the device best, falling back to the others. Raises `ConnectionError` when none can connect, `BLEBusyError` when every source that hears it is leased. `on_disconnect` is called when the connection drops.

The router orders the candidates by:

1. The sources that heard the device within the removal grace window (~11 s), strongest signal first; every source when none did.
2. A source that reports `free_slots == 0` (a proxy out of connection slots) goes last.
3. Leased sources are skipped.

### `exclusive`

```python
async with ble.exclusive(address, owner="myintegration", is_pairing_needed=False) as lease:
    connection = await lease.connect(on_lost)
    ...  # pair, commission, update firmware
```

Leases the source hearing the device best to you, e.g. while pairing it. That source pauses scanning until the block ends, and `connect` calls of others avoid it; every other source keeps working. `lease.connect(on_disconnect)` connects through exactly the leased source (`lease.source`, e.g. `hci0` or `esphome:<mac>`).

A lease **pauses** a source that can (`PausableBLESource`), and stops the others. A proxy is paused, not stopped: it answers connects only while it stays subscribed. Leaving the block releases the source and resumes it (or starts it again). Disconnect before you leave.

A source someone else holds is waited for `wait` seconds (default 1), then the next best is tried, round after round. After `timeout` seconds (default 30) it raises `BLEBusyError`, a `ConnectionError`. With `is_pairing_needed=True` only sources that can pair (`is_pairable`) are leased; when none hears the device it raises `BLEPairingError`.

### `scan_actively`

```python
async def scan_actively(duration: float) -> None: ...
```

Scans actively for `duration` seconds, e.g. in [`start_pairing_window`](../controller.md#start_pairing_windowduration_sec-credentialsnone). Sources scan passively by default: they hear every advertiser and the matchers choose. An active scan also asks for the scan responses, which often carry the name. The router switches each source that can (`ScanModeBLESource`) with `set_scan_mode(is_active)`, before `start` too, and back once the burst ends.

### `devices`

Every device heard recently, as the source hearing it best sees it.

---

## `BLEMatcher`

```python
@dataclass(frozen=True)
class BLEMatcher:
    service_uuid: UUID | None = None          # advertised as a service or in the service data
    service_data_uuid: UUID | None = None     # in the service data only
    manufacturer_id: int | None = None
    manufacturer_data_start: bytes = b""
    local_name_prefix: str | None = None
```

Every field that is set must match; `BLEMatcher()` matches everything. A manufacturer id alone selects protocols that advertise no service UUID, e.g. HomeKit (HAP-BLE) accessories by Apple's company id. Examples:

| Devices | Matcher |
|---|---|
| Matter, commissionable | `BLEMatcher(service_uuid=UUID("0000fff6-0000-1000-8000-00805f9b34fb"))` |
| HomeKit (HAP-BLE) accessories | `BLEMatcher(manufacturer_id=0x004C, manufacturer_data_start=b"\x06")`, or `BLEMatcher(manufacturer_id=0x004C)` for everything Apple advertises |
| ESPHome Improv | `BLEMatcher(service_uuid=UUID("00467768-6228-2272-4663-277478268000"))` |

---

## `BLEDiscoveryListener` (Protocol)

```python
class BLEDiscoveryListener(Protocol):
    async def ble_did_discover_device(self, ble: BLERouter, info: BLEDiscoveryInfo): ...
    async def ble_did_update_device(self, ble: BLERouter, info: BLEDiscoveryInfo): ...
    async def ble_did_remove_device(self, ble: BLERouter, info: BLEDiscoveryInfo): ...
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
    rssi: int | None = None
    last_seen: float = 0.0
```

| Field | Type | Description |
|---|---|---|
| `device` | `BLEDevice` | Bleak device object (`.address`, `.name`) |
| `advertisement` | `AdvertisementData` | Latest advertisement from the source hearing it best (RSSI, manufacturer data, service data, service UUIDs, …) |
| `source` | `str` | That source: `hci0`, `esphome:<mac>`, … |
| `rssi` | `int \| None` | The signal as that source hears it |
| `last_seen` | `float` | When it was last heard (monotonic) |

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
    async def write(self, handle: int, data: bytes, is_response_needed: bool = True) -> None: ...
    async def start_notify(self, handle: int, callback: Callable[[bytes], None]) -> None: ...  # notifications and indications
    async def stop_notify(self, handle: int) -> None: ...
    async def disconnect(self) -> None: ...
```

`mtu` is the one negotiated on connect. On BlueZ, bleak reports 23 until the MTU is acquired, though BlueZ exchanged the real one on connect; the router's local adapter reports the negotiated one (from the characteristics' maximum write size), so a protocol that sizes its segments by `mtu` (Matter's BTP) doesn't run at the 23-byte rate.

---

## Securing the link

Credentials (a Wi-Fi password, a Thread network key) go to a device only over a link a `SecureChannel` (`majordom_integration_sdk.capabilities`) has secured first. Pick one per device and open it on the leased connection:

```python
channel = LESecureConnections()
async with ble.exclusive(address, owner=OWNER, is_pairing_needed=channel.is_pairing_needed) as lease:
    async with channel.secure(await lease.connect()) as connection:
        await connection.write(handle, credentials)
```

| Channel | What it does |
|---|---|
| `LESecureConnections(is_pairing_kept=False)` | Pairs "Just Works" before anything is written, so the link is encrypted, or raises `BLEPairingError` (fail closed). The device decides LE Secure Connections over legacy pairing. It unpairs once done unless `is_pairing_kept` |
| `Unsecured()` | Writes over the link as it is: only for firmware that can't pair, chosen explicitly |

"Just Works" is all a headless Hub can do: it stops passive sniffing, not an active man in the middle during the pairing itself.

A connection that can pair is a `PairableBLEConnection` (`pair()`, `unpair()`). The local adapters pair through BlueZ: LE Secure Connections "Just Works" still asks the host to confirm, and bleak registers no agent, so the pairing would fail ("Numeric comparison failed"). The adapter starts the pairing from a D-Bus connection that holds its own `org.bluez.Agent1` (`NoInputNoOutput`). That agent confirms only the device being paired, and goes away with the connection.

---

## Sources

A source is anything that hears advertisements and can connect: `BLESource` with `name`, `start(on_advertisement)`, `stop()` and `connect(address, on_disconnect)`. The router reads two optional attributes: `is_pairable` (its connections are `PairableBLEConnection`s) and `free_slots` (the connections it can still open, `None` when it can't tell). Two optional protocols:

| Protocol | Methods | Used for |
|---|---|---|
| `PausableBLESource` | `pause_scanning()`, `resume_scanning()` | a lease, without letting go of the radio |
| `ScanModeBLESource` | `set_scan_mode(is_active)` | passive or active scanning |

To lend the router a source of your own (as ESPHome does with its proxies), bring a `BLEProxy(source)` along, see [Bringing peripherals along](../radios.md#bringing-peripherals-along). The runtime binds it to the router and drops it when you stop.

In library mode, `BLEService(sources=[...])` hears through the sources you give it, besides the ones bound to it; `await ble.add_source(source)` and `await ble.remove_source(name)` change them while it runs. In tests, use the doubles from `majordom_integration_sdk.testing` (the `ble` extra):

```python
radio = FakeBLESource("hci0", connection=my_fake_connection, is_pairable=True, free_slots=3)
router = FakeBLERouter(sources=[radio])  # no background tasks
await router.start()
controller = MyController(build_test_platform())
controller.peripherals = Peripherals({"ble": router.endpoint})
radio.advertise("AA:BB:CC:DD:EE:FF", service_data={"0000fff6-0000-1000-8000-00805f9b34fb": payload})
```

To check a `BLEProxy` you bring along, read your controller's `provides` and hand the proxy's source to the router with `router.add_source(proxy.source)`.

---

## Example

```python
_SWITCHBOT = [BLEMatcher(service_uuid=UUID("cba20d00-224d-11e6-9fb8-0002a5d5c51b"))]

# in Controller
needs = [BLE_ROUTER]
...
async def start(self):
    self._ble_cancel = self.peripherals.instance(BLE_ROUTER).register(self, _SWITCHBOT)

async def stop(self):
    self._ble_cancel()

# BLEDiscoveryListener Implementation

async def ble_did_discover_device(self, ble: BLERouter, info: BLEDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.output.controller_did_receive_discovery(self, discovery)

async def ble_did_update_device(self, ble: BLERouter, info: BLEDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.output.controller_did_update_discovery(self, discovery)

async def ble_did_remove_device(self, ble: BLERouter, info: BLEDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        if self._discoveries.pop(discovery.id, None):
            await self.output.controller_did_lose_discovery(self, discovery.id)

async def _read_battery(self, address: str) -> int:
    connection = await self.peripherals.instance(BLE_ROUTER).connect(address)
    try:
        services = await connection.services()
        battery = next(c for s in services for c in s.characteristics if c.uuid.startswith("00002a19"))
        return (await connection.read(battery.handle))[0]
    finally:
        await connection.disconnect()
...
```
