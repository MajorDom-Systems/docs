# Peripherals

An integration never opens `/dev/ttyUSB0`, starts its own Bluetooth scanner, or reads a server URL from an environment variable. It declares what it **needs**, and the Hub hands it over in `self.peripherals` once something can serve it. The same code then works with any supported stick, a multi-PAN radio, or a server running elsewhere.

Everything around an integration is a *peripheral*: a radio, a Bluetooth router, a Docker service, even your controller. Each one `needs` capabilities and `provides` them. A capability is a `family/dialect` pair: the family says what it is (`zigbee`), the dialect how to talk to it (`ezsp`).

## What the SDK provides

### In-process capabilities

Objects you call directly. Need them by the SDK's typed needs, from `majordom_integration_sdk.capabilities`.

| Need | Capability | What you get | Docs |
|---|---|---|---|
| `BLE_ROUTER` | `ble/router` | a `BLERouter`: discovery, connections and leases over every Bluetooth radio | [Bluetooth LE](capabilities/ble.md) |
| `ZEROCONF` | `mdns/zeroconf` | a `Zeroconf` browser (mDNS / DNS-SD) | [Zeroconf](discovery/zeroconf.md) |
| `UPNP_SSDP` | `upnp/ssdp` | an `SSDP` listener | [SSDP](discovery/ssdp.md) |

### Radios

USB sticks the Hub recognises, and radios soldered on the Hub's board. You get a serial path (`/dev/serial/by-id/…`) and its serial settings in `params` (`baud`, `flow_control`).

| Capability | Radio |
|---|---|
| `zigbee/ezsp` | Silicon Labs stick with Zigbee firmware |
| `thread/spinel` | Silicon Labs stick with Thread (RCP) firmware |
| `multipan/silabs-cpc` | Silicon Labs stick with multi-PAN firmware |
| `zwave/serial-api` | any Z-Wave stick |

Other sticks are recognised by the `UsbDriver`s integrations bring (see [Recognising a stick](#recognising-a-stick-usbdriver)).

### Services

Docker services the SDK runs while something needs them.

| Service | Needs | Provides |
|---|---|---|
| `otbr` (OpenThread Border Router) | `thread/spinel` | `thread/otbr-rest`: a Thread border router's REST API, shared |
| `silabs-multiprotocol` | `multipan/silabs-cpc` | `zigbee/ezsp` over TCP and `thread/otbr-rest`, from one multi-PAN stick |

Integrations bring their own services the same way, see [Bringing a Docker service](#tldr-bringing-a-docker-service).

### Host and raw Bluetooth

| Capability | What it is |
|---|---|
| `ip` | the Hub's network, shared by everyone |
| `ble/bluez`, `ble/silabs-cpc-hci`, `ble/esphome-proxy` | raw Bluetooth radios: taken by the router only. Use `BLE_ROUTER` |

Facts about the Hub (radio region, Wi-Fi network, Thread network) aren't peripherals: read them from `self.platform`, see [Settings](settings.md#hub-settings).

[See all peripherals and how they connect →](../hub/peripherals-map.md)

## TL;DR: using a peripheral

Declare `needs`, then read what they are bound to in `start()`:

```python
import dataclasses

from majordom_integration_sdk import AbstractController, Device, Need, Parameter
from majordom_integration_sdk.capabilities import BLE_ROUTER


class AcmeController(AbstractController[Device, Parameter]):
    needs = [
        Need("zigbee", ["ezsp", "znp"]),  # every dialect your library speaks
        dataclasses.replace(BLE_ROUTER, is_required=False),  # optional: works without it
    ]

    async def start(self):
        radio = self.peripherals.endpoint("zigbee")
        self._client = await connect_radio(radio.dialect, radio.url, baud=radio.params.get("baud"))

        if router := self.peripherals.instance(BLE_ROUTER):  # None while unbound
            self._cancel_ble = router.register(self, MATCHERS)
```

| Read | Returns |
|---|---|
| `self.peripherals.endpoint(family)` | the `Endpoint` bound to that need: `url`, `dialect`, `params` |
| `self.peripherals.endpoints(family)` | every endpoint of an `is_many` need, as a list |
| `self.peripherals.instance(NEED)` | the object of a typed need (`BLE_ROUTER`, `ZEROCONF`, `UPNP_SSDP`), or `None` |

Connect to the `url` you're given and never build one yourself: it may point at a stick, a TCP socket, or a server somewhere else.

## TL;DR: bringing a Docker service

When your protocol runs behind a server, ship the server with the integration as a `Service`. The Hub runs it in Docker while your controller runs. Z-Wave is the simple case: zwave-js-server opens the stick, and the controller talks to its WebSocket API.

```python
from majordom_integration_sdk import AbstractController, Device, Endpoint, Need, Parameter, Peripheral, Platform, Service


def zwave_js_server() -> Service:
    return Service(
        "zwave-js-server",
        needs=[Need("zwave", ["serial-api"])],  # the stick
        provides=[Endpoint("zwave", "zwave-js-ws", "ws://127.0.0.1:{ports.api}")],
        ports={"api": 3000},  # preferred: the Hub picks another one when it's taken
        compose={
            "image": "ghcr.io/kpine/zwave-js-server@sha256:…",  # pin by digest
            "network_mode": "host",
            "command": ["server", "/dev/zwave", "--host", "{host.listen_address}", "--port", "{ports.api}"],
            "devices": ["{peripherals.zwave.url}:/dev/zwave"],
            "volumes": ["{data}:/cache"],
            "environment": {"RF_REGION": "{platform.region}"},
        },
    )


class ZwaveController(AbstractController[Device, Parameter]):
    needs = [Need("zwave", ["zwave-js-ws"])]  # what the service provides

    async def start(self):
        url = self.peripherals.endpoint("zwave").url  # ws://127.0.0.1:3000
        ...


def peripherals(platform: Platform) -> list[Peripheral]:
    """The integration's entry point: the Hub runs everything it returns."""
    return [zwave_js_server(), ZwaveController(platform)]
```

That's all: the Hub finds the stick, starts the container with the stick's path, waits until its port answers, and starts the controller with the server's URL. Build a new `Service` on every `peripherals()` call.

`compose` is a [Docker Compose service](https://docs.docker.com/reference/compose-file/services/) (typed as `ComposeService`). Its strings are templates:

| Template | Becomes |
|---|---|
| `{peripherals.<family>.url}` | the URL bound to one of the service's needs, e.g. the stick's path; empty while an optional need is unbound |
| `{peripherals.<family>.params[<name>]}` | a parameter of that endpoint, e.g. `baud` |
| `{ports.<name>}` | the host port the Hub picked for that port |
| `{data}` | the service's own data folder; mount it to keep state |
| `{settings.<field>}` | a field of the service's [settings](settings.md#settings-of-a-service) |
| `{platform.<fact>}` | a Hub fact, e.g. `{platform.region}` |
| `{host.listen_address}` | where a host-network service listens: loopback by default. Listen there, never on `0.0.0.0` |
| `{host.interface}`, `{host.uid}`, `{host.gid}` | the Hub's network interface; its user and group, for a container that writes its data as the Hub |

A format spec renders text by the value: `{x:?text}` renders `text` when `x` isn't empty, `{x:!text}` when it is. A list item that renders empty is left out, so `"volumes": ["{peripherals.ble.url:?/run/dbus:/run/dbus:ro}"]` mounts the system bus only while an adapter is bound. Write `{{` and `}}` for literal braces.

The `params` of the endpoints a service provides are templates too: that's how it tells its consumer what it got, e.g. `params={"adapter": "{peripherals.ble.url}"}`.

The service may be recreated or crash at any time. Keep the controller [reconnecting](controller.md#staying-connected).

## Needs

```python
Need(family, dialects=(), is_required=True, is_many=False)
```

- **Dialects**: list every one your client speaks. With none, any dialect of the family is accepted: only for what the host shares, like `Need("ip")`.
- **Required** (the default): the controller starts once the need is bound, and stops while it's lost. Meanwhile the app shows the integration as waiting for it.
- **Optional** (`is_required=False`): the controller runs without it, and gets it once something can serve it. For a typed need: `dataclasses.replace(BLE_ROUTER, is_required=False)`.
- **Many** (`is_many=True`): every matching endpoint, as a list.

An endpoint is exclusive by default, as a serial port opens once: the first consumer takes it. A shared one (`is_shared=True`), like a border router or `ip`, serves everyone.

## When a peripheral comes or goes

| What happens | The controller |
|---|---|
| A required need is lost (stick unplugged, server gone) | is stopped, and started again once it's back |
| A need appears or moves, an optional one is lost | gets [`needed_peripheral_did_change()`](controller.md#hooks); restarted unless it returns `True` |
| Its settings or the Hub's facts change | gets `settings_did_change()` or `platform_facts_did_change()`, the same way |
| A service it uses restarts | isn't told: it [reconnects](controller.md#staying-connected) itself |

## Bringing peripherals along

A controller's `provides` may hold peripherals too: they run while it does. When the list changes, tell the Hub with `await self.output.controller_did_change_provided(self)`. The common case is a Bluetooth proxy: a device with its own Bluetooth radio, lent to the router as a `BLEProxy`. See [Adding a BLE proxy](capabilities/ble.md#adding-a-ble-proxy).

## Recognising a stick: `UsbDriver`

The Hub recognises Silicon Labs and Z-Wave sticks itself. If your integration talks to a stick directly and it's of another kind, export a `UsbDriver` from `peripherals()`: `identify(path)` returns the firmware the stick runs (or `None` when it isn't yours), and `firmwares` says what each firmware provides, `{device}` being the stick's path.

```python
from majordom_integration_sdk import Endpoint, UsbDriver


class AcmeDriver(UsbDriver):
    name = "acme"
    firmwares = {"acme-zigbee": [Endpoint("zigbee", "acme", "{device}", params={"baud": 115200})]}

    async def identify(self, path: str) -> str | None:
        return "acme-zigbee" if await probe_acme(path) else None
```

The Hub asks each driver once per stick.

## Dependency trees

The Hub resolves a whole chain of needs on its own: a controller needs a service, the service needs a radio or another service. A few more complex cases, as examples.

### Matter: a service, an optional border router, Bluetooth

```text
MatterController            needs matter/matter-server, ble/router (optional)
├── matterjs-server         the integration's own Service: needs ip, thread/otbr-rest (optional)
│   └── otbr                the SDK's Service: needs thread/spinel
│       └── a Thread stick
│     (or silabs-multiprotocol, on a multi-PAN stick)
└── the Bluetooth router    lent to matterjs-server for commissioning
```

matterjs-server needs only `ip`, so Matter runs on any Hub. Its optional Thread need makes the Hub start a border router whenever a stick can serve one; nothing in the integration says which. The border router tells the Hub the Thread network it formed, and the controller reads it as `self.platform.thread_dataset`. Commissioning over Bluetooth holds a [lease](capabilities/ble.md#locking-a-radio-exclusive) for the whole flow.

### Zigbee: one need, many sticks

```text
ZigBeeController            needs zigbee/ezsp | znp | deconz | …
├── a Zigbee stick          zigbee/ezsp at /dev/serial/by-id/…
├── or silabs-multiprotocol zigbee/ezsp at socket://127.0.0.1:9999
│   └── a multi-PAN stick   multipan/silabs-cpc
└── or another stick        recognised by the integration's own UsbDriver, e.g. zigbee/znp
```

The controller reads `self.peripherals.endpoint("zigbee")` and opens whatever it gets: a serial path or a TCP socket, in the dialect it names. Switching from a Zigbee stick to a multi-PAN one needs no change in its code.

## Without the Hub

The standalone runner binds peripherals the same way, or lets you pass them yourself. See [Standalone Mode](standalone.md#connecting-to-radios-and-services).
