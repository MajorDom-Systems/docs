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
        self._router = self.peripherals.instance(BLE_ROUTER)
```

When the integration also works without Bluetooth, make the need optional. `instance()` then returns `None` on a hub without Bluetooth:

```python
needs = [dataclasses.replace(BLE_ROUTER, is_required=False)]
```

## Discovering devices

See [Bluetooth Discovery](../discovery/ble.md): `router.register(listener, matchers)`, with a full example.

`router.devices()` returns every device heard recently, if you need a snapshot instead of events.

## Connecting and using GATT

`connect(address)` opens a GATT connection. Characteristics are addressed by their handle, which you find in `services()`:

```python
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"


async def read_battery(self, address: str) -> int:
    connection = await self._router.connect(address)
    try:
        characteristics = [c for s in await connection.services() for c in s.characteristics]
        battery = next(c for c in characteristics if c.uuid == BATTERY_LEVEL)
        return (await connection.read(battery.handle))[0]
    finally:
        await connection.disconnect()
```

| `BLEConnection` | Does |
|---|---|
| `await services()` | the device's GATT services, each with its `characteristics` (`uuid`, `handle`, `properties`) |
| `await read(handle)` | reads a characteristic, as `bytes` |
| `await write(handle, data, is_response_needed=True)` | writes a characteristic; `False` for "write without response" |
| `await start_notify(handle, callback)` | calls `callback(data)` on every notification or indication |
| `await stop_notify(handle)` | stops them |
| `await disconnect()` | closes the connection |
| `mtu` | the negotiated MTU, to size your packets |

`connect(address, on_disconnect)` calls `on_disconnect()` when the connection drops. It raises `ConnectionError` when no radio can reach the device, and `BLEBusyError` (a `ConnectionError`) when every radio that hears it is leased to someone else.

Always disconnect when you're done: an ESPHome proxy has only a few connection slots.

## Locking a radio: `exclusive`

A short exchange (read a value, send a command) just connects. A long, multi-step setup should lease the radio first, so nobody else's connection or scan gets in the middle:

```python
from majordom_integration_sdk.capabilities import BLEBusyError

try:
    async with self._router.exclusive(address, owner=self.key, timeout=60) as lease:
        connection = await lease.connect()
        try:
            await self._provision(connection)  # several reads, writes and notifications
        finally:
            await connection.disconnect()
except BLEBusyError:
    ...  # tell the user the Hub's Bluetooth is busy, try again later
```

While the block runs, the radio that hears the device best stops scanning and serves only you; the other radios keep working for everyone. When the block ends, the radio goes back to the router. Always connect through `lease.connect()`, not `router.connect()`, inside the block.

| Lock | Don't lock |
|---|---|
| Commissioning or pairing that takes several steps (Matter commissioning, Wi-Fi provisioning over Improv) | Discovery: the router does it for you |
| A firmware update | Reading a value or sending a command |
| Anything that must not lose its radio halfway | Anything over in a second or two |

A lease blocks other integrations from that radio, so hold it no longer than the setup takes.

| Parameter | Meaning |
|---|---|
| `owner` | who holds it, for the logs: your integration's `key` |
| `timeout` | seconds to wait for a free radio before `BLEBusyError` (default 30) |
| `wait` | seconds to wait for the best radio before trying the next one (default 1) |
| `is_pairing_needed` | lease only a radio that can pair (see below); `BLEPairingError` when none hears the device |

## Pairing and sending credentials

Send credentials (a Wi-Fi password, a Thread network key) only over a secured link. Pick a `SecureChannel` and open it on the leased connection:

```python
from majordom_integration_sdk.capabilities import BLEPairingError, LESecureConnections

channel = LESecureConnections()
async with self._router.exclusive(address, owner=self.key, is_pairing_needed=channel.is_pairing_needed) as lease:
    async with channel.secure(await lease.connect()) as connection:
        await connection.write(credentials_handle, credentials)
```

| Channel | Use for |
|---|---|
| `LESecureConnections()` | the default: pairs ("Just Works") before anything is written, and unpairs when the block ends; `LESecureConnections(is_pairing_kept=True)` keeps the bond. Raises `BLEPairingError` when the link can't be encrypted, so nothing is sent unencrypted |
| `Unsecured()` | firmware that can't pair at all; chosen explicitly, it logs a warning |

Not every radio can pair: an ESPHome proxy can't. `is_pairing_needed=True` leases one that can.

## Active scanning in a pairing window

Radios scan passively: they hear every advertisement, but many devices send their name only when asked. While the user is pairing, ask for an active scan:

```python
async def start_pairing_window(self, duration_sec: int, credentials: ProvidedCredentials | None = None):
    await self._router.scan_actively(duration_sec)
```

## Adding a BLE proxy

If your integration talks to devices that have a Bluetooth radio of their own (like ESPHome nodes with `bluetooth_proxy`), it can lend that radio to the router. Every integration then reaches Bluetooth devices through it.

1. Implement `BLESource` for the radio:

    ```python
    from collections.abc import Callable

    from majordom_integration_sdk.capabilities import BLEConnection, OnAdvertisement


    class AcmeBLESource:
        name = "acme-1"  # unique: e.g. the radio's MAC
        is_pairable = False  # True when its connections can pair
        free_slots: int | None = 3  # connections it can still open; None when unknown

        async def start(self, on_advertisement: OnAdvertisement): ...  # call on_advertisement(device, advertisement) for each one heard
        async def stop(self): ...
        async def connect(self, address: str, on_disconnect: Callable[[], None]) -> BLEConnection: ...
    ```

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
