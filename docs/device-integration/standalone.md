# Standalone Mode — Running an Integration Without the Hub

Every MajorDom integration is a self-contained library for its protocol. The Hub is just one
consumer: it constructs your `Controller`, injects its platform and peripherals, and drives it. You can do exactly
the same thing yourself — to script a device, embed an integration in another app, or test against
real hardware — with no Hub involved.

There are three ways to run one, all in `majordom_integration_sdk.dev`:

| | `run_cli(...)` | `run_controller(...)` | `build_platform(...)` |
|---|---|---|---|
| Use for | driving a device by hand from a prompt | watching devices, quick demos | programmatic pair / control / fetch |
| Needs | bound by the runtime, as under the Hub | bound by the runtime | you pass the peripherals, or drive a `Runner` |
| Output | interactive commands + console log | logs discoveries/events to the console | **your delegate** (see below) |
| Blocks | interactive prompt until `exit` | runs until Ctrl-C | you drive the lifecycle |
| Extra deps | `[cli]`, plus the runtime's | `[runtime,ble,discovery]` | none |

`run_cli` and `run_controller` start the SDK runtime for the controller, as the Hub does: the
Bluetooth router over the local adapters, DNS-SD, SSDP, the radios it finds and the services it runs
in Docker. The controller starts once its required needs are bound, stops when one is lost, and
hears about moved peripherals, settings and context through its hooks, restarting unless they
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
from integration_template.controller import ExampleController  # your controller

asyncio.run(run_cli(ExampleController, db_path="devices.db"))
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
from integration_template.controller import ExampleController  # your controller

asyncio.run(run_controller(ExampleController, db_path="devices.db"))
```

A need that stays unbound is logged with its reason, e.g. `ble isn't bound: need ble/bluez: every
provider taken by ble-router — use Need("ble", ["router"])`.

## Programmatic mode — `build_platform` + call the controller

For anything beyond watching — pair a device, send a command, fetch state — build the platform
yourself and call the controller's methods directly:

```python
import asyncio
from majordom_integration_sdk import Endpoint
from majordom_integration_sdk.dev import build_platform
from majordom_integration_sdk.schemas.credentials import ProvidedCredentials
from integration_template.controller import ExampleController

async def main():
    platform = build_platform(integration=ExampleController.name, db_path="devices.db")
    controller = ExampleController(platform, {"example": Endpoint("example", "echo", "socket://127.0.0.1:7000")})
    await controller.start()
    # ... await controller.pair_device(discovery, ProvidedCredentials(...)), send_command, fetch ...
    await controller.stop()

asyncio.run(main())
```

To have the runtime bind the needs instead, drive the controller through a `Runner`, as
`run_controller` does:

```python
from pathlib import Path
from majordom_integration_sdk.dev import Runner, build_platform, build_runtime

runtime = build_runtime(ExampleController, Path(".majordom-dev/runtime"), docker=False)
runner = Runner(ExampleController, build_platform(integration=ExampleController.name), runtime)
await runner.start()  # starts the runtime; the controller starts once its required needs are bound
controller = runner.controller
...
await runner.stop()
```

## Connecting to radios and services

An integration with [`needs`](radios.md) gets its peripherals from the runtime, standalone as
under the Hub. How much of it runs is up to you:

| Level | You run | The runtime runs | Pass |
|---|---|---|---|
| Full | nothing | everything: providers, radios, services in Docker | nothing |
| Partial | some of it, e.g. your own border router or no Docker | the rest | `pinned={...}`, `docker=False`, `scan=False` |
| Bare | the radio or server | nothing (library mode) | `peripherals={...}` |

### Full: everything automatic

```python
asyncio.run(run_controller(ZigBeeController))
```

The runtime finds sticks, identifies them, binds every need, runs the services, and keeps watching.
It keeps its state and the services' data in `.majordom-dev/runtime` (under `storage_root=`).
Services need Docker, and recognising Silicon Labs sticks needs the `universal-silabs-flasher`
command on `PATH`.

### Partial: no Docker, no radios, your own servers

On a machine without Docker or radios, turn those off and pin what you run yourself. An endpoint you
pin is offered as written, ahead of anything the runtime finds, and no container starts for a need
it serves:

```python
import asyncio
from majordom_integration_sdk import Endpoint
from majordom_integration_sdk.dev import run_controller
from majordom_zwave import ZwaveController

asyncio.run(run_controller(
    ZwaveController,
    docker=False,  # run the containers yourself; the runtime still writes the compose.json it would have run
    scan=False,  # the stick lives behind your zwave-js-server
    pinned={"zwave": Endpoint("zwave", "zwave-js-ws", "ws://localhost:3000")},
))
```

The router, DNS-SD and SSDP still run in-process, so discovery works without Docker. Pin `thread`
(`Endpoint("thread", "otbr-rest", "http://my-otbr:8081", is_shared=True)`) to keep matterjs-server
running here, but behind your border router. In the CLI, `pin` and `unpin` do the same while it runs.

Under the runtime, settings and context come from it, as under the Hub: change them with
`runtime.update_settings(scope, values)` (see [Settings](settings.md)).

### Bare: pass the peripherals yourself

You already have the stick or the server, or don't want the runtime at all. Hand the controller its
peripherals; the runtime doesn't start, and nothing is bound or rebound:

```python
asyncio.run(run_controller(ZigBeeController, peripherals={"zigbee": Endpoint("zigbee", "ezsp", "/dev/ttyUSB0")}))
```

`run_controller` and `run_cli` then also take any field of `Platform` as a keyword argument, e.g.
`settings=` or `context=Context(wifi=WifiCredentials("Home", "password"))`, the network to
commission devices onto.

A need for DNS-SD, SSDP or the router then takes an instance you start yourself, e.g.
`{"ble": BLEService().endpoint}` (`majordom_integration_sdk.runtime.peripherals.providers.ble.router`).
You run the servers here, so `platform.services.restart()` raises `NotImplementedError`. Restart the
server yourself; the controller [reconnects](controller.md#restarting-your-service-and-healing) on
its own.

### The runtime as a library

The runner wraps `majordom_integration_sdk.runtime.Runtime`, which you can also drive yourself, for
several controllers at once:

```python
from pathlib import Path
from majordom_integration_sdk import Endpoint
from majordom_integration_sdk.runtime import Runtime

runtime = Runtime(
    Path("radios"),  # where it keeps its state and the services' data
    {"matter": MatterController, "zwave": ZwaveController},  # by slug, bound in this order
    pinned={"zwave": Endpoint("zwave", "zwave-js-ws", "ws://my-zwave:3000")},
    scan=False,  # or devices={"stick": "/dev/ttyUSB0"}: this device only
)
await runtime.start()  # starts the providers, finds sticks, binds, runs services, keeps watching
runtime.peripherals("matter")  # {"matter": Endpoint("matter", "matter-server", "ws://127.0.0.1:5580"), "ble": …}; None while a required need is unbound
runtime.unbound("matter")  # why each unbound need isn't bound, by family
platform = runtime.platform("matter", build_platform())  # its settings, the context, its services and offers
```

| Call | Does |
|---|---|
| `peripherals(slug)` | the consumer's bound needs, a `Peripherals`; `None` while a required need can't be met |
| `unbound(owner)` | why each need of a consumer, service or provider isn't bound, with a hint when there is something to do |
| `providers(owner)` | who serves each bound need |
| `platform(slug, base)` | `base` with the consumer's settings, the context, its `services` and `offers` |
| `pin(family, provider)`, `pin_endpoint(endpoint)` | prefer a radio or service, or provide an endpoint yourself |
| `reserve(owner, family, url)` | keep one endpoint for one consumer, ahead of the router ([Reservations](../hub/radios.md#reservations)) |
| `offer(owner, endpoint)`, `withdraw(owner, endpoint)` | what a consumer lends others; a controller does it through `platform.offers` |
| `refresh()` | look for radios again and bind anew |

`Runtime(builtins=[...])` picks the in-process providers; by default one of each whose extra is
installed. Pass `on_change=` to hear about every rebinding, and read `peripherals()` and `context()`
again there; that is what `Runner` does. The Thread dataset, for example, reaches `context()` only
once the border router has a network.

## The platform

`build_platform()` returns the same `Platform` the Hub injects. Its main fields:

- **`output`** — the *delegate* the controller calls to report discoveries, connections, and events
  (a `ControllerOutput`). Defaults to a console logger; pass your own to actually receive them (next
  section).
- **`make_device_repository`** — an async-context factory for the device store. `db_path=` selects a
  file-backed SQLite repository (state survives restarts); omit it for an in-memory one. Scoped to
  your integration via `integration=`.
- **`documents_folder`** — a `Path` your controller may write files into (per-integration subtree).
- **`settings`**, **`context`** — the controller's [settings](settings.md) and hub-wide facts.
  The runtime fills them (`Runtime.platform`); `None` and empty without it, or pass them as shown
  [above](#connecting-to-radios-and-services).
- **`services`**, **`offers`** — the runtime's hold on your services and your offers; without the
  runtime, `restart()` raises `NotImplementedError` and offers go nowhere.

Discovery and radios are not here: they are needs, bound into `self.peripherals`.

```python
platform = build_platform(
    integration=ExampleController.name,
    db_path="devices.db",   # omit for in-memory
    output=MyDelegate(),    # see below
)
```

## Receiving discoveries & events — implement a delegate

The controller doesn't *return* discoveries and events; it **pushes** them to `platform.output`. To act
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
    platform = build_platform(integration=ExampleController.name, db_path="devices.db", output=delegate)
    controller = ExampleController(platform, peripherals)  # bound by hand, or drive it through a Runner
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

Subclassing `LoggingControllerOutput` gives every method a logging default, so you only implement
the ones you care about.

## Testing without real devices

For tests, prefer the offline doubles in `majordom_integration_sdk.testing` —
`build_test_platform()` (in-memory repository, temp-dir storage) plus `RecordingControllerOutput`
(captures discoveries/events for assertions), and `FakeZeroconf`, `FakeSSDP`, `FakeBLERouter` with
`FakeBLESource`s and `FakeOffers` for the peripherals — over `build_platform` and real hardware. See
[Example Integration](example-integration.md#testing) and any integration's `tests/`.
