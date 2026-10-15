# Connecting to Radios and Services

An integration never opens `/dev/ttyUSB0` itself or reads a server URL from an environment variable. It declares what it needs, and the Hub hands it an address once something can serve that need. The Hub finds the USB sticks, recognises their firmware, runs the services between radios and integrations, and binds them together. Moving from one stick to another, or to a multi-PAN radio, needs no change in your code.

The language lives in the SDK ([`transport.py`](https://github.com/MajorDom-Systems/integration-sdk/tree/master/majordom_integration_sdk/transport.py)). The Hub's side lives in [`majordom-transports`](https://github.com/MajorDom-Systems/majordom-transports); see [Radios and Transports](../hub/radios.md) for how it works inside.

## Capabilities

A capability is a `family/dialect` pair. The family says what it is (`zigbee`, `thread`); the dialect says how to talk to it (`ezsp`, `otbr-rest`).

| Capability | What it is | Offered by | Used by |
|---|---|---|---|
| `zigbee/ezsp` | Silicon Labs EmberZNet | a Silicon Labs stick with Zigbee firmware, or the `multiprotocol` service | Zigbee |
| `zigbee/znp`, `zigbee/deconz`, `zigbee/xbee`, `zigbee/zigate`, `zigbee/cc` | other Zigbee coordinators | a stick the Zigbee integration's `probe()` recognises | Zigbee |
| `thread/spinel` | a Thread radio (RCP) | a Silicon Labs stick with Thread firmware | `otbr` service |
| `thread/otbr-rest` | a Thread border router's REST API (shared) | `otbr` or `multiprotocol` service | `matter-server` (optional), ESPHome (optional) |
| `cpc/uart` | a Silicon Labs multi-PAN radio | a Silicon Labs stick with multi-PAN firmware | `multiprotocol` service |
| `matter/ws` | matter-server's WebSocket API | `matter-server` service | Matter |
| `zwave/serial` | a Z-Wave controller (Serial API) | any Z-Wave stick | `zwave-js` service |
| `zwave/ws` | Z-Wave JS server's WebSocket API | `zwave-js` service | Z-Wave |
| `ip` | the hub's network (shared) | the host | `matter-server` |
| `ble` | the hub's Bluetooth (shared) | the host | Matter (optional) |

`multiprotocol` runs one multi-PAN stick as both a Zigbee coordinator and a Thread border router. `otbr` is a border router on a plain Thread stick. Both come with `majordom-transports`; `matter-server` and `zwave-js` come with the Matter and Z-Wave integrations.

## Needs

A need is what your integration requires from its environment: a dependency that something else (a radio, a server, the hub's network) must provide.

```python
@dataclass(frozen=True)
class Need:
    family: str
    dialects: Sequence[str] = ()  # empty: any dialect of the family
    required: bool = True
```

- `Need("zigbee")` accepts any dialect of the family. Read the bound dialect from `links["zigbee"].dialect`.
- `Need("matter", ["ws"])` accepts only the listed dialects.

A need is **required** by default. The Hub starts the integration only once every required need is bound, and stops it when one is lost. Meanwhile the Hub reports the integration as waiting for its radio.

An **optional** need (`required=False`) doesn't hold the integration back. The Hub binds it when it can. Until then it is missing from `dependencies.links`.

## Endpoints

```python
@dataclass(frozen=True)
class Endpoint:
    family: str
    dialect: str = ""
    url: str = ""
    shared: bool = False
```

An endpoint is what a radio, a service or the host offers, and what your controller receives in `dependencies.links`. `url` is what you connect to: a serial path (`/dev/serial/by-id/usb-…`), a TCP socket (`socket://127.0.0.1:9999`) or a WebSocket (`ws://127.0.0.1:5580/ws`).

- **Exclusive** (the default): one consumer only. A serial port opens once, so a stick's endpoints are exclusive.
- **Shared**: any number of consumers. One border router serves both Matter and ESPHome; `ip` serves everyone.

When several providers can serve a need, endpoints you pin in library mode win, then the provider the user picked for that family, then the host, radios and services, in that order.

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

A service is what your integration provides to its environment: a companion server it brings along. When your protocol runs behind a server (Matter behind matter-server, Z-Wave behind Z-Wave JS), declare that server as a `Service`, list it in your controller's `services`, and need what it provides. The Hub runs the service only while something is bound to one of its endpoints, and stops it when nothing is.

`compose` is the service's [Docker Compose](https://docs.docker.com/reference/compose-file/services/) definition: image, environment, volumes, and so on. The Hub adds `restart: unless-stopped` and runs it in the `majordom` Compose project. There's no `depends_on`: every service retries until the links it needs answer. Pin the image by digest so an upstream release can't change what runs.

Strings in `compose` are templates:

| Template | Becomes |
|---|---|
| `{data}` | the service's own data folder on the hub; mount it to keep state |
| `{links.<family>.url}` | the URL bound to one of the service's needs, e.g. `{links.zwave.url}` is the stick's path; empty while an optional need is unbound |
| `{links.<family>.params[<name>]}` | a serial parameter of that link, such as `baud`, when the board profile sets one |
| `{ports.<name>}` | the host port the runtime picked for the service's port `<name>` |
| `{settings.<field>}` | a field of the service's `settings` |
| `{context.region}` | the hub's radio region |
| `{host.interface}` | the hub's network interface: a wired one with a link, else the one of the default route |
| `{host.uid}`, `{host.gid}` | the hub's user and group, for a container that should write its data as the hub |

A value of `None` renders empty. Write `{{` and `}}` for literal braces. (`{device}`, a stick's path, belongs to the radio drivers in `majordom-transports`, not to services.)

Run the service on the host network and name the ports it listens on. `ports={"api": 5580}` says which host port it *prefers*, not a fixed one: the runtime uses it when free and otherwise assigns another (45800–45999), keeps the choice across restarts, and fills `{ports.<name>}` in the compose and in the `provides` URLs. Pass the port to the server through `compose` (an environment variable or a command-line argument), and write `{ports.<name>}` in the URLs it provides. See [Matter](#matter-with-its-own-service) for a complete service.

Your integration never reads a port: it connects to `dependencies.links[<family>].url`. That URL may not even point at your service. When the user runs their own server and pins it as the provider, the Hub doesn't run yours and hands over the pinned URL instead, with no change in your code.

## Recognising a stick: `probe()`

```python
@classmethod
async def probe(cls, path: str) -> Endpoint | None: ...
```

The Hub recognises Silicon Labs and Z-Wave sticks itself. For any other stick, it asks each integration's `probe()` whether the stick at `path` speaks one of its protocols. Return what the stick offers then, or `None`. The Hub remembers the answer, so it asks once per stick. Only integrations that talk to a radio directly need it.

## Examples

### Zigbee: a radio, directly

Zigbee talks to the coordinator itself through zigpy, so it needs `zigbee` in any dialect and recognises sticks the Hub doesn't know ([`controller.py`](https://github.com/MajorDom-Systems/integration-zigbee/tree/master/majordom_zigbee/controller.py)):

```python
class ZigBeeController(AbstractController):
    needs = [Need("zigbee")]  # any zigpy dialect: ezsp, znp, deconz, xbee, zigate, cc
    settings = ZigBeeSettings

    @classmethod
    async def probe(cls, path: str) -> Endpoint | None:
        found = await detect({CONF_DEVICE_PATH: path})
        return Endpoint("zigbee", found[0].key, path) if found else None

    async def start(self):
        link = self.dependencies.links["zigbee"]
        settings = cast(ZigBeeSettings, self.dependencies.settings or ZigBeeSettings())
        self._zigbee_device_path = link.url
        ...
        # Start the zigpy application of the radio library the bound dialect names.
        application_cls = await resolve_application(config[CONF_DEVICE], requested=link.dialect)
```

What it gets depends on the stick:

| Stick | `links["zigbee"]` |
|---|---|
| Silicon Labs, Zigbee firmware | `Endpoint("zigbee", "ezsp", "/dev/serial/by-id/usb-…")` |
| Silicon Labs, multi-PAN firmware | `Endpoint("zigbee", "ezsp", "socket://127.0.0.1:9999")`, through the `multiprotocol` service |
| Texas Instruments, recognised by `probe()` | `Endpoint("zigbee", "znp", "/dev/serial/by-id/usb-…")` |

### Matter: with its own service

Matter drives matter-server over its WebSocket API, so it brings matter-server along as a service ([`config.py`](https://github.com/MajorDom-Systems/integration-matter/tree/master/majordom_matter/config.py)):

```python
MATTER_SERVER = Service(
    "matter-server",
    # Thread is optional: without a border router Matter still works over Wi-Fi and Ethernet.
    needs=[Need("ip"), Need("thread", ["otbr-rest"], required=False)],
    provides=[Endpoint("matter", "ws", "ws://127.0.0.1:{ports.api}/ws")],
    ports={"api": 5580},  # preferred: another one when 5580 is taken
    compose={
        "image": "ghcr.io/matter-js/matterjs-server@sha256:…",
        "network_mode": "host",
        "userns_mode": "host",
        "user": "{host.uid}:{host.gid}",  # its data folder belongs to the hub
        "environment": {
            "STORAGE_PATH": "/data",
            "PORT": "{ports.api}",  # the server listens where the runtime says
            "BLE_PROXY": "true",  # Bluetooth comes from the hub
        },
        "volumes": ["{data}:/data"],
    },
)
```

The controller needs only what the service provides, and hands the hub's networks to matter-server for commissioning ([`controller.py`](https://github.com/MajorDom-Systems/integration-matter/tree/master/majordom_matter/controller.py)):

```python
class MatterController(AbstractController):
    needs = [Need("matter", ["ws"]), Need("ble", required=False)]  # Bluetooth for commissioning
    services = [MATTER_SERVER]

    async def start(self):
        ...
        # ws://127.0.0.1:5580/ws, or wherever the server runs: never build this URL yourself
        self._matter_client = MatterClient(self.dependencies.links["matter"].url, self._matter_client_session)
        await self._matter_client.connect()
        ...
        # Networks new devices get commissioned onto.
        if wifi := self.dependencies.context.wifi:
            await self._matter_client.set_wifi_credentials(wifi.ssid, wifi.password)
        if dataset := self.dependencies.context.thread_dataset:
            await self._matter_client.set_thread_operational_dataset(dataset)
```

Matter brings matter-server (its service) but needs a Thread border router, which it doesn't bring: `majordom-transports` does, as its `otbr` service (`multiprotocol` on a multi-PAN stick). The Hub binds the chain from the controller down:

| Consumer | Needs | Bound to | Gets |
|---|---|---|---|
| `MatterController` | `matter/ws` | `matter-server`, Matter's own service | `dependencies.links["matter"].url`: `ws://127.0.0.1:5580/ws`, or another port when 5580 is taken |
| `matter-server` | `thread/otbr-rest` (optional) | `otbr`, from `majordom-transports` | `{links.thread.url}` in its compose: `http://127.0.0.1:8081` |
| `otbr` | `thread/spinel` | a Thread stick | `{links.thread.url}` in its compose: the stick's path |

A controller that declares `Need("thread", ["otbr-rest"])` itself, as ESPHome does [below](#esphome-an-optional-border-router), finds the same URL in `dependencies.links["thread"].url`.

`matter-server` needs only `ip` to run, so Matter starts on any hub. Its optional Thread need makes the Hub run a border router whenever a stick can serve one. The Hub then learns the Thread network from the border router and passes it in `context.thread_dataset`; the context changes, and as Matter doesn't handle that in place (see [`context_did_change()`](controller.md#context_did_changebefore)), the Hub restarts it, and it hands the dataset to matter-server.

If the user already runs a matter-server, they pin it as the `matter` provider. The Hub then doesn't run `MATTER_SERVER` and hands the controller that server's URL instead.

Z-Wave follows the same pattern: its `zwave-js` service needs `zwave/serial` from the stick and provides `zwave/ws`, which the controller needs ([`config.py`](https://github.com/MajorDom-Systems/integration-zwave/tree/master/majordom_zwave/config.py)).

### ESPHome: an optional border router

ESPHome devices on Wi-Fi need nothing. Devices on Thread reach the hub over IP through a border router ([`controller.py`](https://github.com/MajorDom-Systems/integration-esphome/tree/master/majordom_esphome/controller.py)):

```python
class ESPhomeController(AbstractController[ESPhomeDevice, ESPhomeParameter]):
    name = "esphome"
    # Devices on Thread reach the hub through a border router; Wi-Fi devices need nothing.
    needs = [Need("thread", ["otbr-rest"], required=False)]
```

The controller never reads the link. Declaring it is enough: the Hub runs a border router when a stick can serve Thread, and ESPHome runs either way.

## When a radio comes or goes

- A required link is lost (the stick is unplugged, or switched to other firmware): the Hub stops the integration and tells the user it resumes when the radio is back. It starts again once the need is bound.
- A link appears or moves, or an optional one is lost: the Hub calls [`peripheral_did_change()`](controller.md#peripheral_did_changechange). Unless it returns `True`, the Hub restarts the integration with the new links.
- Settings or context change: the Hub calls [`settings_did_change()`](controller.md#settings_did_changebefore) or [`context_did_change()`](controller.md#context_did_changebefore): return `True` when applied in place; the default (`False`) has the Hub restart the integration.
- One of your services restarts (you [restarted it](controller.md#restarting-your-service-and-healing), or it crashed): the Hub isn't involved and the integration keeps running. Reconnect to it yourself.

## Without the Hub

Standalone, you pass the links yourself, or let `majordom-transports` find them. See [Standalone Mode](standalone.md#connecting-to-radios-and-services).
