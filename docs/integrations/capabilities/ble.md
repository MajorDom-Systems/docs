# Bluetooth LE

Everything an integration does over Bluetooth goes through one object: the `BLERouter`.

## What the router is

The Hub may have several Bluetooth radios: its own adapter, a USB dongle, the Bluetooth of a multi-PAN stick, and ESPHome nodes acting as Bluetooth proxies around the house. The router holds all of them and gives every integration one API:

- **Discovery**: you say which devices you want to hear about, and it reports them, whichever radio heard them.
- **Connections**: you connect by address, and it picks the radio that hears the device best.
- **Leases**: you lock one radio to one device for a long setup, while the others keep working for everyone.

Your code never knows which radio carries a connection. A device in the garage reached through an ESPHome proxy works the same as one next to the Hub.

!!! danger "Never access Bluetooth hardware directly"
    Don't open adapters, scan or connect with bleak, BlueZ, `bluetoothctl` or any other library or service. The router already holds every radio: a direct scan competes with it, misses the proxies, and can break another integration's pairing. A need for raw Bluetooth (`Need("ble", ["bluez"])`) is never bound while the router runs.

## Getting the router

Need `BLE_ROUTER`, and read it from `self.peripherals`:

```python
from majordom_integration_sdk.capabilities import BLE_ROUTER


class AcmeController(AbstractController[Device, Parameter]):
    needs = [BLE_ROUTER]

    async def start(self):
        self._ble = self.peripherals.instance(BLE_ROUTER)
```

When the integration also works without Bluetooth, make the need optional. `instance()` then returns `None` on a hub without Bluetooth:

```python
needs = [BLE_ROUTER(is_required=False)]
```

## Discovering devices

See [Bluetooth Discovery](../discovery/ble.md): `router.register(listener, matchers)`, with a full example.

`router.devices()` returns every device heard recently, if you need a snapshot instead of events.

## Connecting and using GATT

`connect(address)` opens a GATT connection for the block, and closes it when the block ends. Characteristics are addressed by their handle, which you find in `services()`:

```python
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"


async def read_battery(self, address: str) -> int:
    async with self._ble.connect(address) as connection:
        characteristics = [c for s in await connection.services() for c in s.characteristics]
        battery = next(c for c in characteristics if c.uuid == BATTERY_LEVEL)
        return (await connection.read(battery.handle))[0]
```

| `BLEConnection` | Does |
|---|---|
| `await connection.services()` | the device's GATT services, each with its `characteristics` (`uuid`, `handle`, `properties`) |
| `await connection.read(handle)` | reads a characteristic, as `bytes` |
| `await connection.write(handle, data, is_response_needed=True)` | writes a characteristic; `False` for "write without response" |
| `await connection.start_notify(handle, callback)` | calls `callback(data)` on every notification or indication |
| `await connection.stop_notify(handle)` | stops them |
| `await connection.disconnect()` | closes the connection before the block ends |
| `connection.mtu` | the negotiated MTU, to size your packets |

| `connect(…)` parameter | Meaning |
|---|---|
| `on_disconnect` | called when the connection drops |
| `busy_timeout` | seconds to reach the device, waiting for a radio leased to someone else (default 10). Then `BLEBusyError` when every radio that hears it is still leased, or `ConnectionError` (which `BLEBusyError` also is) when none reaches it |
| `max_duration` | seconds after which the connection is closed and the block gets `TimeoutError` (default 600); `None` keeps it open, only when you mean it |

Every Bluetooth radio has only a few connection slots, a proxy fewer still: keep the block short. When a connection must outlive a block, like a subscription kept while the integration runs, `open_connection(…, max_duration=None)` takes the same parameters and returns the connection: disconnect it yourself.

## Locking a radio: `exclusive`

A short exchange (read a value, send a command) just connects. A long, multi-step setup should lease the radio first, so nobody else's connection or scan disrupts the operation:

```python
from majordom_integration_sdk.capabilities import BLEBusyError

try:
    async with self._ble.exclusive(address, owner=self.key, max_duration=300) as lease, lease.connect() as connection:
        await self._provision(connection)  # several reads, writes and notifications
except BLEBusyError:
    ...  # tell the user the Hub's Bluetooth is busy, try again later
```

While the block runs, the radio that hears the device best stops scanning and serves only you; the other radios keep working for everyone. When the block ends, the radio goes back to the router. Always connect through `lease.connect()`, not `self._ble.connect()`, inside the block; it takes the same parameters.

| Lock | Don't lock |
|---|---|
| Commissioning or pairing that takes several steps (Matter commissioning, Wi-Fi provisioning over Improv) | Discovery: the router does it for you |
| A firmware update | Reading a value or sending a command |
| Anything that must not lose its radio halfway | Anything over in a second or two |

A lease blocks other integrations from that radio, so hold it no longer than the setup takes.

| Parameter | Meaning |
|---|---|
| `owner` | who holds it, for the logs: your integration's `key` |
| `busy_timeout` | seconds to wait for a free radio before `BLEBusyError` (default 30) |
| `max_duration` | seconds the lease holds the radio; then the block gets `TimeoutError` and the radio goes back (default 120) |
| `wait` | seconds to wait for the best radio before trying the next one (default 1) |
| `is_pairing_needed` | lease only a radio that can pair (see below); `BLEPairingError` when none hears the device |

## Pairing and sending credentials

Send credentials (a Wi-Fi password, a Thread network key) only over a secured link. Pick a `SecureChannel` and open it on the leased connection:

```python
from majordom_integration_sdk.capabilities import BLEPairingError, LESecureConnections

channel = LESecureConnections()
async with self._ble.exclusive(address, owner=self.key, is_pairing_needed=channel.is_pairing_needed) as lease:
    async with lease.connect() as connection, channel.secure(connection) as secured:
        await secured.write(credentials_handle, credentials)
```

| Channel | Use for |
|---|---|
| `LESecureConnections()` | the default: pairs ("Just Works") before anything is written, and unpairs when the block ends; `LESecureConnections(is_pairing_kept=True)` keeps the bond. Raises `BLEPairingError` when the link can't be encrypted, so nothing is sent unencrypted |
| `Unsecured()` | firmware that can't pair at all; chosen explicitly, it logs a warning |

Not every radio can pair: a source says it can with `is_pairable`. `is_pairing_needed=True` leases one that can.


## Adding a BLE proxy

If your integration talks to devices that have a Bluetooth radio of their own (like ESPHome nodes with `bluetooth_proxy`), it can lend that radio to the router. Every integration then reaches Bluetooth devices through it.

1. Implement `BLESource` for the radio:

    ```python
    from collections.abc import Callable

    from majordom_integration_sdk.capabilities import BLEConnection, GattService, OnAdvertisement


    class AcmeBLESource:
        name = "acme-1"  # unique: e.g. the radio's MAC
        is_pairable = False  # True when its connections can pair
        free_slots: int | None = 3  # connections it can still open; None when unknown

        async def start(self, on_advertisement: OnAdvertisement): ...  # call on_advertisement(device, advertisement) for each one heard
        async def stop(self): ...
        async def connect(self, address: str, on_disconnect: Callable[[], None]) -> BLEConnection:
            return AcmeBLEConnection(await self._radio.connect(address), on_disconnect)  # pseudo


    class AcmeBLEConnection:
        """Wraps one GATT connection of the radio: the router hands it to integrations as a `BLEConnection`."""

        mtu: int

        async def services(self) -> list[GattService]: ...
        async def read(self, handle: int) -> bytes: ...
        async def write(self, handle: int, data: bytes, is_response_needed: bool = True): ...
        async def start_notify(self, handle: int, callback: Callable[[bytes], None]): ...
        async def stop_notify(self, handle: int): ...
        async def disconnect(self): ...  # call on_disconnect() when the radio reports the link dropped, too
    ```

    A radio whose connections can pair returns `PairableBLEConnection`s (with `pair()` and `unpair()`) and sets `is_pairable = True`.

    A source that can stop scanning without letting go of its radio also implements `pause_scanning()` and `resume_scanning()`; one that can switch to active scanning implements `set_scan_mode(is_active)`. The router uses them when they are there.

2. Provide it as a `BLEProxy` while the radio is reachable, and tell the Hub each time that changes:

    ```python
    from majordom_integration_sdk.peripherals import BLEProxy


    class AcmeController(AbstractController[Device, Parameter]):
        @property
        def provides(self) -> list[BLEProxy]:
            return list(self._proxies.values())

        async def _on_node_connected(self, node_id: str, source: AcmeBLESource):
            self._proxies[node_id] = BLEProxy(source)
            await self.output.controller_did_change_provided(self)

        async def _on_node_lost(self, node_id: str):
            if self._proxies.pop(node_id, None):
                await self.output.controller_did_change_provided(self)
    ```

Keep `BLEProxy`'s default dialect: the router hears through proxies as `ble/esphome-proxy`, whoever brings them. It starts hearing through the proxy at once, and lets it go when you take it back or the integration stops. See [Peripherals](../peripherals.md#bringing-peripherals-along) for providing peripherals in general.

## Testing

The SDK's test doubles (the `ble` extra) run a real router over fake radios:

```python
from majordom_integration_sdk import Peripherals
from majordom_integration_sdk.testing import FakeBLERouter, FakeBLESource, build_test_platform

radio = FakeBLESource("hci0", connection=my_fake_connection, is_pairable=True)
router = FakeBLERouter(sources=[radio])
await router.start()

controller = AcmeController(build_test_platform())
controller.peripherals = Peripherals({"ble": router.endpoint})
await controller.start()

radio.advertise("AA:BB:CC:DD:EE:FF", local_name="Acme", service_uuids=["0000fd00-0000-1000-8000-00805f9b34fb"])
```

To test a proxy you provide, hand its source to the router: `await router.add_source(controller.provides[0].source)`.
