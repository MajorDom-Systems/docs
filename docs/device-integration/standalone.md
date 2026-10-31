# Standalone Mode — Running an Integration Without the Hub

Every MajorDom integration is a self-contained library for its protocol. The Hub is just one
consumer: it calls your package's `peripherals(platform)`, binds their needs, and drives them. You can do exactly
the same thing yourself — to script a device, embed an integration in another app, or test against
real hardware — with no Hub involved.

There are three ways to run one, all in `majordom_integration_sdk.dev`:

| | `run_cli(...)` | `run_controller(...)` | `build_platform(...)` |
|---|---|---|---|
| Use for | driving a device by hand from a prompt | watching devices, quick demos | programmatic pair / control / fetch |
| Needs | bound by the runtime, as under the Hub | bound by the runtime | you hand over `Peripherals`, or drive a `Runner` |
| Output | interactive commands + console log | logs discoveries/events to the console | **your delegate** (see below) |
| Blocks | interactive prompt until `exit` | runs until Ctrl-C | you drive the lifecycle |
| Extra deps | `[cli]`, plus the runtime's | `[runtime,ble,discovery]` | none |

`run_cli` and `run_controller` start the SDK runtime for the controller, as the Hub does: the
Bluetooth router over the local adapters, Zeroconf, SSDP, the radios it finds and the services it runs
in Docker (`default_peripherals()`). The controller starts once its required needs are bound, stops when one is lost, and
hears about moved peripherals, settings and platform facts through its hooks, restarting unless they
handle them. The runtime needs its extras:

```sh
pip install "majordom-integration-sdk[runtime,ble,discovery]"
```

Without them, the runner stops with that install hint, or pass `peripherals={...}` yourself (see
[below](#connecting-to-radios-and-services)).

## Interactive CLI — `run_cli`

The fastest way to actually *use* an integration by hand: it starts the controller under the
runtime with a local device store, then drops you into a prompt to pair, control, and inspect
devices, and to see or pin what its needs are bound to. It's the MajorDom Hub's operator CLI, scoped
to a single integration.

The interactive CLI needs one more extra (typer-shell + rich), so install the `cli` extra too:

```sh
pip install "majordom-integration-sdk[cli,runtime,ble,discovery]"
```

```python
# cli.py
import asyncio
from majordom_integration_sdk.dev import run_cli
import integration_template  # your integration

asyncio.run(run_cli(integration_template.peripherals, db_path="devices.db"))
```

```sh
python cli.py
```

```text
example > help          # list commands
example > discoveries   # devices seen on the network (id, name, transport, expected credentials)
example > pair <discovery_id> [credentials_type] [credentials_value]
example > pair_window 60 # open a join window (Zigbee); no-op where discovery is continuous
example > devices        # paired devices (id, name, available)
example > device <id>    # its parameters (id, name, role, visibility, value)
example > control <device_id> <parameter_id> <value>   # value parsed as JSON if possible
example > identify <device_id>   # blink/beep
example > fetch <device_id>      # refresh state from the device
example > unpair <device_id>
example > needs          # each need: what it is bound to and by whom, or why it isn't bound
example > pin <family> <url> [dialect]   # provide an endpoint yourself, e.g. pin zigbee socket://192.168.1.5:6638 ezsp
example > unpin <family>  # drop it: the runtime binds the need again
example > resolve        # look for radios again and bind every need anew
example > exit
```

`needs` prints one line per need:

```text
zigbee/ezsp|znp|deconz|…  -> /dev/serial/by-id/usb-…  by usb-…
ble/router (optional)  -> router  by ble-router
thread/otbr-rest (optional)  unbound: need thread/otbr-rest: nothing offers it
```

`pin` takes the need's first dialect when you give none (`pin matter ws://127.0.0.1:5580`); its
endpoint is shared and wins over anything the runtime finds. `pin`, `unpin` and `resolve` need the
runtime: with `peripherals=` given by hand they raise.

Pass `db_path=` to keep paired devices across restarts (a file-backed store); omit it for an
in-memory one. Under the hood this is exactly the wiring described below — the same
`build_platform` and runtime plus a delegate that persists state — so anything the CLI does you can
also do in code.

## Watch mode — `run_controller`

The quickest way to see an integration work. It starts the runtime for your controller, a
file-backed device store, and a console logger, then runs your controller until interrupted:

```python
import asyncio
from majordom_integration_sdk.dev import run_controller
import integration_template  # your integration

asyncio.run(run_controller(integration_template.peripherals, db_path="devices.db"))
```

A need that stays unbound is logged with its reason, e.g. `ble isn't bound: need ble/bluez: every
provider taken by ble-router — use Need("ble", ["router"])`.

## Programmatic mode — build the platform, call the controller

For anything beyond watching — pair a device, send a command, fetch state — build the platform
yourself and call the controller's methods directly (library mode):

```python
import asyncio
from majordom_integration_sdk import Endpoint, Peripherals
from majordom_integration_sdk.dev import build_platform
from integration_template.controller import ExampleController

async def main():
    controller = ExampleController(build_platform(db_path="devices.db"))
    controller.peripherals = Peripherals({"example": Endpoint("example", "echo", "tcp://127.0.0.1:7000")})
    controller.output = MyDelegate()  # see below; logs by default
    await controller.start()
    # ... await controller.pair_device(discovery, ProvidedCredentials(...)), send_command, fetch ...
    await controller.stop()

asyncio.run(main())
```

To have the runtime bind the needs instead, use `build_runtime` and a `Runner`, as `run_controller`
does:

```python
from pathlib import Path
from majordom_integration_sdk.dev import Runner, build_platform, build_runtime

platform = build_platform()
exported = integration_template.peripherals(platform)
controller = next(p for p in exported if isinstance(p, ExampleController))
runner = Runner(controller, build_runtime(exported, Path(".majordom-dev/runtime"), platform=platform))
await runner.start()  # starts the runtime; the controller starts once its required needs are bound
...
await runner.stop()
```

## Connecting to radios and services

An integration with [`needs`](radios.md) gets its peripherals from the runtime, standalone as
under the Hub. How much of it runs is up to you:

| Level | You run | The runtime runs | Pass |
|---|---|---|---|
| Full | nothing | `default_peripherals()`: providers, radios, services in Docker | nothing |
| Partial | some of it, e.g. your own border router or no Docker | what you list | `pinned=[...]`, `runtime_peripherals=[...]` |
| Bare | the radio or server | nothing (library mode) | `peripherals={...}` |

### Full: everything automatic

```python
asyncio.run(run_controller(majordom_zigbee.peripherals))
```

The runtime finds sticks, identifies them, binds every need, runs the services, and keeps watching.
It keeps its state and the services' data in `.majordom-dev/runtime` (under `storage_root=`).
Services need Docker, and recognising Silicon Labs sticks needs the `universal-silabs-flasher`
command on `PATH`.

### Partial: no Docker, no radios, your own servers

On a machine without Docker or radios, run only the peripherals you want and pin what you run
yourself. A pinned endpoint wins over anything the runtime finds, and no container starts for a need
it serves:

```python
import asyncio
import majordom_zwave
from majordom_integration_sdk import Endpoint
from majordom_integration_sdk.dev import run_controller
from majordom_integration_sdk.runtime import HostNetwork

asyncio.run(run_controller(
    majordom_zwave.peripherals,
    runtime_peripherals=[HostNetwork()],  # no USB scanning, no Docker
    pinned=[Endpoint("zwave", "zwave-js-ws", "ws://localhost:3000")],  # your zwave-js-server
))
```

Pin `thread` (`Endpoint("thread", "otbr-rest", "http://my-otbr:8081", is_shared=True)`) to keep
matterjs-server running here, but behind your border router. In the CLI, `pin` and `unpin` do the
same while it runs.

Under the runtime, settings come from it, as under the Hub: change them with
`runtime.update_settings(peripheral, values)` (see [Settings](settings.md)). Platform facts are
keyword arguments: `run_controller(..., region="Europe")`.

### Bare: pass the peripherals yourself

You already have the stick or the server, or don't want the runtime at all. Hand the controller its
peripherals; the runtime doesn't start, and nothing is bound or rebound:

```python
asyncio.run(run_controller(
    majordom_zigbee.peripherals,
    peripherals={"zigbee": Endpoint("zigbee", "ezsp", "/dev/ttyUSB0")},
))
```

`run_controller` and `run_cli` also take any field of `Platform` as a keyword argument, e.g.
`wifi=WifiCredentials("Home", "password")`, the network to commission devices onto.

A typed need for Zeroconf, SSDP or the router then takes an instance you start yourself, as
`Endpoint("mdns", "zeroconf", instance=zeroconf)`. You run the servers here: restart them yourself;
the controller [reconnects](controller.md#staying-connected) on its own.

### The runtime as a library

The runner wraps `majordom_integration_sdk.runtime.Runtime`, which you can also drive yourself, for
several integrations at once. It runs peripherals in the order given:

```python
from pathlib import Path
from majordom_integration_sdk import Endpoint
from majordom_integration_sdk.runtime import Pinned, Runtime, default_peripherals

platform = build_platform()
runtime = Runtime(
    Path("runtime"),  # where it keeps its state and the services' data
    [
        Pinned(Endpoint("zwave", "zwave-js-ws", "ws://my-zwave:3000")),
        *default_peripherals(),
        *majordom_matter.peripherals(platform),
        *majordom_zwave.peripherals(platform),
    ],
    platform=platform,
)
await runtime.start()  # starts what is wanted, binds, runs services, keeps watching
matter = runtime.peripheral("matter")
runtime.bound(matter)  # {"matter": Endpoint("matter", "matter-server", "ws://127.0.0.1:5580"), …}
runtime.unbound(matter)  # why each unbound need isn't bound, by family
```

| Call | Does |
|---|---|
| `peripheral(key)`, `peripherals()` | one peripheral by its key; every one, in binding order |
| `status(p)` | its state (waiting, running, failed, …) and why |
| `bound(p)`, `unbound(p)`, `providers(p)` | what its needs are bound to, why not, and by whom |
| `enable(p)`, `disable(p)`, `restart(p)` | the user's switches; `DisabledStore` keeps them by key |
| `update_settings(p, values)` | validate, store and apply new settings |
| `update_platform(platform)` | new platform facts, handed to every peripheral |
| `refresh()` | look for radios again and bind anew |

Pass `output=` (a `RuntimeOutput`) to hear about every change of status and what peripherals learn.

## The platform

`build_platform()` returns a `Platform` like the Hub's: frozen, the same for every peripheral.

- **`device_repository(p)`** — one unit of work on the device store, scoped to the peripheral's key.
  `db_path=` selects a file-backed SQLite repository; omit it for an in-memory one.
- **`documents_folder(p)`** — a folder per peripheral key under `storage_root` (`.majordom-dev`).
- **`region`**, **`wifi`**, **`thread_dataset`** — the host's facts; set them with
  `dataclasses.replace(platform, region="Europe")`.

The controller's output, settings and needs are not on the platform: they are `self.output`,
`self.settings` and `self.peripherals`.

## Receiving discoveries & events — implement a delegate

The controller doesn't *return* discoveries and events; it **pushes** them to `self.output`. To act
on them in standalone mode, pass an object implementing the `ControllerOutput` protocol. The
simplest path is to subclass the SDK's `LoggingControllerOutput` and override only what you need:

```python
import asyncio
from majordom_integration_sdk.dev import LoggingControllerOutput, build_platform
from majordom_integration_sdk.schemas.credentials import CredentialsType, ProvidedCredentials
from integration_template.controller import ExampleController

class MyDelegate(LoggingControllerOutput):
    def __init__(self):
        self.discoveries = {}

    async def controller_did_receive_discovery(self, controller, discovery):
        self.discoveries[discovery.id] = discovery

    async def controller_did_receive_events(self, controller, events):
        for event in events:
            print("event:", event)

async def main():
    delegate = MyDelegate()
    controller = ExampleController(build_platform(db_path="devices.db"))
    controller.peripherals = peripherals  # bound by hand, or drive it through a Runner
    controller.output = delegate
    await controller.start()

    # wait for the first discovery, then pair it
    while not delegate.discoveries:
        await asyncio.sleep(0.2)
    discovery = next(iter(delegate.discoveries.values()))
    device_id = await controller.pair_device(
        discovery, ProvidedCredentials(type=CredentialsType.code, value="123-45-678")
    )

    # ... controller.send_command(...), controller.fetch(device), controller.identify(device) ...

    await controller.stop()

asyncio.run(main())
```

The full delegate surface — every method the controller may call:

| Method | Called when |
|---|---|
| `controller_did_receive_discovery(controller, discovery)` | a new device is discovered |
| `controller_did_update_discovery(controller, discovery)` | a known discovery's details change |
| `controller_did_lose_discovery(controller, discovery_id)` | a discovery is gone |
| `controller_did_connect_device(controller, device_id)` | a paired device comes online (incl. after pairing) |
| `controller_did_lose_device(controller, device_id)` | a paired device goes offline |
| `controller_did_receive_events(controller, events)` | the device reports parameter changes (`DeviceParameterChange`) |
| `controller_did_encounter_error(controller, error)` / `controller_did_resolve_error(controller, error_id)` | an `IntegrationError` is active / gone |
| `controller_did_emit_notification(controller, notification)` | a user-facing notification |
| `controller_did_change_provided(controller)` | what it `provides` changed (the runtime takes this one) |

Subclassing `LoggingControllerOutput` gives every method a logging default, so you only implement
the ones you care about.

## Testing without real devices

For tests, prefer the offline doubles in `majordom_integration_sdk.testing` —
`build_test_platform()` (in-memory repository, temp-dir storage) plus `RecordingControllerOutput`
(captures discoveries/events for assertions), and `FakeZeroconf`, `FakeSSDP`, `FakeBLERouter` with
`FakeBLESource`s, `FakeCompose` and `FakePeripheral` for the peripherals — over `build_platform` and real hardware. See
[Example Integration](example-integration.md#testing) and any integration's `tests/`.
