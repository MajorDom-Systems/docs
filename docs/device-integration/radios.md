# Connecting to Radios and Services

An integration never opens `/dev/ttyUSB0` itself or reads a server URL from an environment variable. It declares what it needs, and the Hub hands it an address, or an object, once something can serve that need. The Hub finds the USB sticks, recognises their firmware, runs the services between radios and integrations and the peripherals it keeps in its own process (the Bluetooth router, DNS-SD, SSDP), and binds them together. Moving from one stick to another, or to a multi-PAN radio, needs no change in your code.

The language lives in the SDK ([`majordom_integration_sdk.peripherals`](https://github.com/MajorDom-Systems/integration-sdk/tree/master/majordom_integration_sdk/peripherals): `Need`, `Endpoint`, `Service`, `Peripherals`, `PeripheralChange`). The side that binds them is the SDK runtime, `majordom_integration_sdk.runtime` (the `runtime` extra), which the Hub and the standalone runner run; see [The SDK Runtime](../hub/radios.md) for how it works inside.

## Capabilities

A capability is a `family/dialect` pair. The family says what it is (`zigbee`, `thread`); the dialect says how to talk to it (`ezsp`, `otbr-rest`). A dialect names the exact protocol or API, after its spec or the implementation that defines it (an upstream server, or a library: `mdns/zeroconf` is a browser over python-zeroconf), so one client library implements it. It is never a transport word (`uart`, `serial`, `ws`, `tcp`): the transport is the URL scheme (`/dev/…`, `socket://`, `ws://`, `http://`).

| Capability | What it is | Offered by | Used by |
|---|---|---|---|
| `zigbee/ezsp` | Silicon Labs EmberZNet | a Silicon Labs stick with Zigbee firmware, or the `silabs-multiprotocol` service | Zigbee |
| `zigbee/znp`, `zigbee/deconz`, `zigbee/xbee`, `zigbee/zigate`, `zigbee/ziggurat`, `zigbee/blz`, `zigbee/cc` | other Zigbee coordinators | a stick the Zigbee integration's `probe()` recognises | Zigbee |
| `thread/spinel` | a Thread radio (RCP) | a Silicon Labs stick with Thread firmware | `otbr` service |
| `thread/otbr-rest` | a Thread border router's REST API (shared) | `otbr` or `silabs-multiprotocol` service | `matterjs-server` (optional), ESPHome (optional) |
| `multipan/silabs-cpc` | a Silicon Labs multi-PAN radio | a Silicon Labs stick with multi-PAN firmware | `silabs-multiprotocol` service |
| `matter/matter-server` | the python-matter-server API, which matterjs-server implements; the URL is its base, with the WebSocket API at `/ws` and the BLE proxy at `/ble` | `matterjs-server` service | Matter |
| `zwave/serial-api` | a Z-Wave controller (Serial API) | any Z-Wave stick | `zwave-js-server` service |
| `zwave/zwave-js-ws` | zwave-js-server's WebSocket API | `zwave-js-server` service | Z-Wave |
| `ip` | the hub's network (shared) | the host | `matterjs-server` |
| `ble/router` | the [Bluetooth router](discovery/ble.md): every radio, one API (shared) | the runtime, in-process | Matter, ESPHome (optional) |
| `ble/bluez` | one Bluetooth adapter of the hub (`hci0`, `hci1`, …), each its own endpoint | the host | the router; `matterjs-server` when one is [reserved](#reservations) for it |
| `ble/silabs-cpc-hci` | the Bluetooth of a multi-PAN radio, when its firmware has it | a Silicon Labs stick with multi-PAN firmware | the router |
| `ble/esphome-proxy` | an ESPHome node's Bluetooth proxy | the ESPHome integration, [offered](#offering-endpoints) while it runs | the router |
| `mdns/zeroconf` | [DNS-SD over mDNS](discovery/zeroconf.md) (shared) | the runtime, in-process | HomeKit, ESPHome |
| `upnp/ssdp` | [SSDP](discovery/ssdp.md) (shared) | the runtime, in-process | — |

`silabs-multiprotocol` runs one multi-PAN stick as both a Zigbee coordinator and a Thread border router. `otbr` is a border router on a plain Thread stick. Both come with the SDK runtime; `matterjs-server` and `zwave-js-server` come with the Matter and Z-Wave integrations. `ble/majordom` is kept for a future MajorDom Bluetooth chip.

## Needs

A need is what your integration requires from its environment: a dependency that something else (a radio, a server, the hub's network, the Bluetooth router, DNS-SD) must provide. Declare everything external as one.

```python
@dataclass(frozen=True)
class Need:
    family: str
    dialects: Sequence[str] = ()  # empty: any dialect of the family
    is_required: bool = True
    is_many: bool = False
```

- `Need("matter", ["matter-server"])` accepts only the listed dialects. List every dialect your client speaks: Zigbee lists every zigpy radio library's (`ZIGPY_DIALECTS`) and reads the bound one from `self.peripherals.endpoint("zigbee").dialect`.
- `Need("ip")`, with no dialects, accepts any: only for what the host shares.
- `is_many=True` binds every matching endpoint that is free, as a list (`self.peripherals.endpoints(family)`). The Bluetooth router needs raw Bluetooth this way, to hear through every radio.

A need is **required** by default. The Hub starts the integration only once every required need is bound, and stops it when one is lost. Meanwhile the Hub reports the integration as waiting for its radio.

An **optional** need (`is_required=False`) doesn't hold the integration back. The Hub binds it when it can. Until then it is missing from `self.peripherals`.

An unbound need carries the reason, for the user and for you: `need zigbee/ezsp|znp|…: nothing offers it`, or, when what took the endpoint offers the same family itself, what to need instead: `need ble/bluez: every provider taken by ble-router — use Need("ble", ["router"])`. The Hub shows it on the integration (`unbound` in [`GET /v1/api/integrations`](../hub/radios.md#rest-api)); standalone, the `needs` command prints it.

## Endpoints

```python
@dataclass(frozen=True)
class Endpoint:
    family: str
    dialect: str = ""
    url: str = ""
    is_shared: bool = False
    params: Mapping[str, Any] = field(default_factory=dict)
    instance: Any = None  # not compared
```

An endpoint is what a radio, a service, the host, the runtime or another integration offers, and what your controller receives in `self.peripherals`. `url` is what you connect to: a serial path (`/dev/serial/by-id/usb-…`), a TCP socket (`socket://127.0.0.1:9999`) or a WebSocket base (`ws://127.0.0.1:5580`). `params` says how to talk to it, e.g. a serial port's `baud` and `flow_control`, or a host adapter's `index`.

`instance` carries an in-process peripheral itself: the Bluetooth router, the DNS-SD browser, an ESPHome node's Bluetooth source. `url` still names it (`router`, an `hciN`), and two endpoints are the same when all but the instance match. Read it with `self.peripherals.instance(family)`.

- **Exclusive** (the default): one consumer only. A serial port opens once, so a stick's endpoints are exclusive.
- **Shared**: any number of consumers. One border router serves both Matter and ESPHome; `ip` serves everyone.

When several providers can serve a need, an endpoint [reserved](#reservations) for this consumer wins, then endpoints you pin, then the provider the user picked for that family, then the host, radios, services, the runtime's own peripherals and what integrations offer, in that order.

The runtime binds its own peripherals first, then the integrations in order, each with the services it reaches. An exclusive endpoint goes to the first consumer that takes it, so the router, which needs every raw Bluetooth adapter, gets them all.

### Reservations

A reservation keeps one endpoint for one consumer (an integration or a service), bound to it before anyone else, the runtime's `is_many` needs included: e.g. `ble/bluez hci1` for `matterjs-server` to use directly, ahead of the router. The user sets it with [`PUT /v1/api/hardware/reservations/{owner}/{family}`](../hub/radios.md#rest-api) (`{"url": "hci1"}`; `null` gives it back); in library mode, `await runtime.reserve(owner, family, url)`. Others see the endpoint as `reserved for <owner>`.

### In-process peripherals

The runtime runs the Bluetooth router (`ble/router`), DNS-SD (`mdns/zeroconf`) and SSDP (`upnp/ssdp`) in its own process, and offers each as a shared endpoint with its `instance`. Need them like any other:

```python
needs = [Need("mdns", ["zeroconf"]), Need("ble", ["router"], is_required=False)]

async def start(self):
    zeroconf: Zeroconf = self.peripherals.instance("mdns")
    self._cancel = zeroconf.register(self, {"_myprotocol._tcp.local."})
    if router := self.peripherals.instance("ble"):  # None on a hub without Bluetooth
        self._cancel_ble = router.register(self, [MY_SERVICE_UUID])
```

Their contracts (`Zeroconf`, `SSDP`, `BLERouter`, …) are in `majordom_integration_sdk.capabilities`; see [Discovery Services](discovery/index.md).

### Offering endpoints

An integration may offer endpoints to others while it runs, through `self.platform.offers`:

```python
await self.platform.offers.offer(Endpoint("ble", "esphome-proxy", node_mac, instance=ble_source))
await self.platform.offers.withdraw(endpoint)  # same family and url
```

The runtime binds an offer like any other endpoint and tells whoever gets or loses it. The ESPHome integration offers each node with `bluetooth_proxy` as `ble/esphome-proxy`, its Bluetooth source as the instance; the router picks it up. An offerer is never bound to its own offer. Without the runtime (library mode) offers go nowhere; in tests, `FakeOffers` records them.

## Bringing your own service

```python
@dataclass(frozen=True)
class Service:
    name: str
    compose: Mapping[str, Any]
    needs: Sequence[Need] = ()
    provides: Sequence[Endpoint] = ()
    settings: type[BaseModel] | None = None
    ports: Mapping[str, int] = field(default_factory=dict)  # name -> preferred host port
```

A service is what your integration provides to its environment: a companion server it brings along. When your protocol runs behind a server (Matter behind matterjs-server, Z-Wave behind zwave-js-server), declare that server as a `Service`, list it in your controller's `services`, and need what it provides. The Hub runs the service only while something is bound to one of its endpoints, and stops it when nothing is.

`compose` is the service's [Docker Compose](https://docs.docker.com/reference/compose-file/services/) definition: image, environment, volumes, and so on. The Hub adds `restart: unless-stopped` and runs it in the `majordom` Compose project. There's no `depends_on`: every service retries until the endpoints it needs answer. Pin the image by digest so an upstream release can't change what runs.

Strings in `compose` are templates:

| Template | Becomes |
|---|---|
| `{data}` | the service's own data folder on the hub; mount it to keep state |
| `{peripherals.<family>.url}` | the URL bound to one of the service's needs, e.g. `{peripherals.zwave.url}` is the stick's path; empty while an optional need is unbound; the first endpoint of an `is_many` need |
| `{peripherals.<family>.params[<name>]}` | a parameter of that endpoint: a serial port's `baud` or `flow_control`, a host Bluetooth adapter's `index`; empty when it has none |
| `{ports.<name>}` | the host port the runtime picked for the service's port `<name>` |
| `{settings.<field>}` | a field of the service's `settings` |
| `{context.region}` | the hub's radio region |
| `{host.interface}` | the hub's network interface: a wired one with a link, else the one of the default route |
| `{host.uid}`, `{host.gid}` | the hub's user and group, for a container that should write its data as the hub |

A value of `None` renders empty. A format spec renders text by the value: `{x:&uart-flow-control}` renders `&uart-flow-control` when the flag `x` is true, `{x:!true}` renders `true` when `x` is empty, e.g. `"BLE_PROXY": "{peripherals.ble.url:!true}"` turns the proxy on while no adapter is bound, and `{x:?dbus}` renders `dbus` when `x` isn't empty. A list item that renders empty is left out, so `"volumes": ["{data}:/data", "{peripherals.ble.url:?/run/dbus:/run/dbus:ro}"]` mounts the system bus only while an adapter is bound. Write `{{` and `}}` for literal braces. (`{device}`, a stick's path, belongs to the radio drivers in the runtime, not to services.)

The `params` of the endpoints a service `provides` are templates too, rendered the same way. That is how a consumer learns what its service got: matterjs-server provides `params={"adapter": "{peripherals.ble.url}"}`, so Matter reads `self.peripherals.endpoint("matter").params["adapter"]`, empty while no adapter is bound to the service. When it changes, the consumer's `matter` endpoint changes, and the Hub calls [`peripheral_did_change()`](controller.md#peripheral_did_changechange).

Run the service on the host network and name the ports it listens on. `ports={"api": 5580}` says which host port it *prefers*, not a fixed one: the runtime uses it when free and otherwise assigns another (45800–45999), keeps the choice across restarts, and fills `{ports.<name>}` in the compose and in the `provides` URLs. Pass the port to the server through `compose` (an environment variable or a command-line argument), and write `{ports.<name>}` in the URLs it provides. See [Matter](#matter-with-its-own-service) for a complete service.

Your integration never reads a port: it connects to `self.peripherals.endpoint(<family>).url`. That URL may not even point at your service. When the user runs their own server and pins it as the provider, the Hub doesn't run yours and hands over the pinned URL instead, with no change in your code.

## Recognising a stick: `probe()`

```python
@classmethod
async def probe(cls, path: str) -> Endpoint | None: ...
```

The Hub recognises Silicon Labs and Z-Wave sticks itself. For any other stick, it asks each integration's `probe()` whether the stick at `path` speaks one of its protocols. Return what the stick offers then, or `None`. The Hub remembers the answer, so it asks once per stick. Only integrations that talk to a radio directly need it.

## Examples

### Zigbee: a radio, directly

Zigbee talks to the coordinator itself through zigpy, so it needs `zigbee` in every dialect zigpy speaks and recognises sticks the Hub doesn't know ([`controller.py`](https://github.com/MajorDom-Systems/integration-zigbee/tree/master/majordom_zigbee/controller.py)):

```python
class ZigBeeController(AbstractController):
    needs = [Need("zigbee", ZIGPY_DIALECTS)]  # ezsp, znp, deconz, xbee, zigate, ziggurat, blz, cc
    settings = ZigBeeSettings

    @classmethod
    async def probe(cls, path: str) -> Endpoint | None:
        found = await detect({CONF_DEVICE_PATH: path})
        return Endpoint("zigbee", found[0].key, path) if found else None

    async def start(self):
        link = self.peripherals.endpoint("zigbee")
        settings = cast(ZigBeeSettings, self.platform.settings or ZigBeeSettings())
        self._zigbee_device_path = link.url
        ...
        # Start the zigpy application of the radio library the bound dialect names.
        application_cls = await resolve_application(config[CONF_DEVICE], requested=link.dialect)
```

What it gets depends on the stick:

| Stick | `self.peripherals.endpoint("zigbee")` |
|---|---|
| Silicon Labs, Zigbee firmware | `Endpoint("zigbee", "ezsp", "/dev/serial/by-id/usb-…")` |
| Silicon Labs, multi-PAN firmware | `Endpoint("zigbee", "ezsp", "socket://127.0.0.1:9999")`, through the `silabs-multiprotocol` service |
| Texas Instruments, recognised by `probe()` | `Endpoint("zigbee", "znp", "/dev/serial/by-id/usb-…")` |

### Matter: with its own service

Matter drives matterjs-server over its WebSocket API, so it brings matterjs-server along as a service ([`config.py`](https://github.com/MajorDom-Systems/integration-matter/tree/master/majordom_matter/config.py)):

```python
MATTERJS_SERVER = Service(
    "matterjs-server",
    # Thread is optional: without a border router Matter still works over Wi-Fi and Ethernet. Bluetooth too: an adapter
    # of its own only when one is reserved for it. The router is an in-process object a container can't bind: it
    # reaches matterjs-server through the controller (ble_delegate, over /ble) instead.
    needs=[Need("ip"), Need("thread", ["otbr-rest"], is_required=False), Need("ble", ["bluez"], is_required=False)],
    # the base URL: /ws, /ble; "adapter" tells the controller whether an adapter is bound here (empty: none)
    provides=[
        Endpoint("matter", "matter-server", "ws://127.0.0.1:{ports.api}", params={"adapter": "{peripherals.ble.url}"})
    ],
    ports={"api": 5580},  # preferred: another one when 5580 is taken
    compose={
        "image": "ghcr.io/matter-js/matterjs-server@sha256:…",
        "network_mode": "host",
        "userns_mode": "host",
        "user": "{host.uid}:{host.gid}",  # its data folder belongs to the hub
        "environment": {
            "STORAGE_PATH": "/data",
            "PORT": "{ports.api}",  # the server listens where the runtime says
            "BLE_PROXY": "{peripherals.ble.url:!true}",  # Bluetooth comes from the hub, unless an adapter is reserved
            "BLUETOOTH_ADAPTER": "{peripherals.ble.params[index]}",
            "NOBLE_BINDINGS": "{peripherals.ble.url:?dbus}",  # an adapter goes through the host's BlueZ, not as root
        },
        "volumes": [
            "{data}:/data",
            "{peripherals.ble.url:?/run/dbus:/run/dbus:ro}",  # the system bus only with an adapter: gone without one
        ],
    },
)
```

The controller needs what the service provides and the router, and hands the hub's networks to matterjs-server for commissioning ([`controller.py`](https://github.com/MajorDom-Systems/integration-matter/tree/master/majordom_matter/controller.py)):

```python
class MatterController(AbstractController):
    # matter: matterjs-server's base URL (its API at /ws, its BLE proxy at /ble);
    # ble: the router, which MatterServerBLEDelegate lends matterjs-server for commissioning
    needs = [Need("matter", ["matter-server"]), Need("ble", ["router"], is_required=False)]
    services = [MATTERJS_SERVER]

    async def start(self):
        ...
        # ws://127.0.0.1:5580, or wherever the server runs: never build the base URL yourself
        self._matter_client = MatterClient(f"{self._server_url}/ws", self._matter_client_session)
        await self._matter_client.connect()
        ...
        # Bluetooth follows the bindings: an adapter of matterjs-server's own, else the router, else none
        if self.peripherals.endpoint("matter").params.get("adapter"):
            await self._offer_commissioning_by_code()
        elif router := self.peripherals.instance("ble"):
            ...  # lent to matterjs-server's /ble
        # Networks new devices get commissioned onto.
        if wifi := self.platform.context.wifi:
            await self._matter_client.set_wifi_credentials(wifi.ssid, wifi.password)
        if dataset := self.platform.context.thread_dataset:
            await self._matter_client.set_thread_operational_dataset(dataset)
```

Matter brings matterjs-server (its service) but needs a Thread border router, which it doesn't bring: the SDK runtime does, as its `otbr` service (`silabs-multiprotocol` on a multi-PAN stick). The Hub binds the chain from the controller down:

| Consumer | Needs | Bound to | Gets |
|---|---|---|---|
| `MatterController` | `matter/matter-server` | `matterjs-server`, Matter's own service | `self.peripherals.endpoint("matter").url`: `ws://127.0.0.1:5580`, or another port when 5580 is taken |
| `MatterController` | `ble/router` (optional) | the runtime's router | `self.peripherals.instance("ble")`, lent to matterjs-server's `/ble` |
| `matterjs-server` | `thread/otbr-rest` (optional) | `otbr`, from the SDK runtime | `{peripherals.thread.url}` in its compose: `http://127.0.0.1:8081` |
| `matterjs-server` | `ble/bluez` (optional) | an adapter [reserved](#reservations) for it, else unbound | `{peripherals.ble.params[index]}` in its compose; the controller sees it as the `adapter` param of its `matter` endpoint |
| `otbr` | `thread/spinel` | a Thread stick | `{peripherals.thread.url}` in its compose: the stick's path |

A controller that declares `Need("thread", ["otbr-rest"])` itself, as ESPHome does [below](#esphome-an-optional-border-router-and-offers), finds the same URL in `self.peripherals.endpoint("thread").url`.

`matterjs-server` needs only `ip` to run, so Matter starts on any hub. Its optional Thread need makes the Hub run a border router whenever a stick can serve one. The Hub then learns the Thread network from the border router and passes it in `context.thread_dataset`; the context changes, and as Matter doesn't handle that in place (see [`context_did_change()`](controller.md#context_did_changebefore)), the Hub restarts it, and it hands the dataset to matterjs-server.

If the user already runs a matter-server, they pin it as the `matter` provider. The Hub then doesn't run `MATTERJS_SERVER` and hands the controller that server's URL instead.

See [Matter](../integrations/matter.md#bluetooth) for its two Bluetooth modes. Z-Wave follows the same pattern: its `zwave-js-server` service needs `zwave/serial-api` from the stick and provides `zwave/zwave-js-ws`, which the controller needs ([`config.py`](https://github.com/MajorDom-Systems/integration-zwave/tree/master/majordom_zwave/config.py)).

### ESPHome: an optional border router, and offers

ESPHome nodes are found over mDNS. Devices on Thread reach the hub over IP through a border router; Wi-Fi devices need nothing more ([`controller.py`](https://github.com/MajorDom-Systems/integration-esphome/tree/master/majordom_esphome/controller.py)):

```python
class ESPhomeController(AbstractController[ESPhomeDevice, ESPhomeParameter]):
    name = "esphome"
    # Nodes are found over mDNS. Devices on Thread reach the hub through a border router; Wi-Fi devices need nothing.
    # The router sets unprovisioned nodes up over Improv BLE; the nodes that proxy Bluetooth are offered back to it.
    needs = [
        Need("mdns", ["zeroconf"]),
        Need("thread", ["otbr-rest"], is_required=False),
        Need("ble", ["router"], is_required=False),
    ]
```

The controller never reads the Thread endpoint. Declaring it is enough: the Hub runs a border router when a stick can serve Thread, and ESPHome runs either way. Each connected node with `bluetooth_proxy` is [offered](#offering-endpoints) as `ble/esphome-proxy`, and the router hears through it.

## When a radio comes or goes

- A required need is lost (the stick is unplugged, or switched to other firmware): the Hub stops the integration and tells the user it resumes when the radio is back. It starts again once the need is bound.
- A bound need appears or moves, or an optional one is lost: the Hub calls [`peripheral_did_change()`](controller.md#peripheral_did_changechange). Unless it returns `True`, the Hub restarts the integration with the new peripherals.
- Settings or context change: the Hub calls [`settings_did_change()`](controller.md#settings_did_changebefore) or [`context_did_change()`](controller.md#context_did_changebefore): return `True` when applied in place; the default (`False`) has the Hub restart the integration.
- One of your services restarts (you [restarted it](controller.md#restarting-your-service-and-healing), or it crashed): the Hub isn't involved and the integration keeps running. Reconnect to it yourself.

## Without the Hub

Standalone, the dev runner starts the runtime to bind them as the Hub does, or you pass the peripherals yourself. See [Standalone Mode](standalone.md#connecting-to-radios-and-services).
