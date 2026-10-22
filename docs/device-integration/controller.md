# Implementing a Controller

!!! tip "Start from the template"
    Scaffold your integration from the
    [`integration-template`](https://github.com/MajorDom-Systems/integration-template)
    (**Use this template → Create a new repository**), and read the
    [Example Integration](example-integration.md) walkthrough alongside this page — it puts every
    piece below together in one worked controller.

## AbstractController Overview

Your integration's controller subclasses [`AbstractController`](https://github.com/MajorDom-Systems/integration-sdk/tree/master/majordom_integration_sdk/controller/abstract_controller.py) from the SDK. It is generic over your `Device` and `Parameter` subclasses:

```python
from majordom_integration_sdk.controller import AbstractController
from majordom_integration_sdk.schemas import Device, Parameter

class MyController(AbstractController[Device, Parameter]):
    name = "My Protocol"  # optional — auto-derived from the class name ("My") otherwise
    ...
```

### The `name` and `slug()` identity

Declare `name` as a **class attribute** (not a property):

```python
class MyController(AbstractController[Device, Parameter]):
    name = "Hue"
```

The Hub reads `name` — and the derived `slug()` (a `@final` classmethod returning the URL-safe slug, e.g. `"hue"`) — off the *class*, before it ever constructs the controller, to wire that integration's documents folder and scoped repository. Because of that, `name` must be a class attribute; the SDK raises a `TypeError` pointing here if it's missing. Read `name_slug`/`slug()` anywhere you need the stable identifier.

### Hub → Device

Implement all abstract methods defined in [`AbstractController`](https://github.com/MajorDom-Systems/integration-sdk/tree/master/majordom_integration_sdk/controller/abstract_controller.py) — `start`, `stop`, `pair_device`, `unpair`, `identify`, `fetch`, `send_command`, and the `discoveries` property. The Hub calls these to drive your integration.

### Device → Hub

Use `self.dependencies.output` (a `ControllerOutput`), injected by the Hub:

```python
# New unpaired device found during discovery
await self.dependencies.output.controller_did_receive_discovery(self, discovery)

# An already-discovered (unpaired) device changed its advertisement
await self.dependencies.output.controller_did_update_discovery(self, discovery)

# A previously-discovered device is no longer visible
await self.dependencies.output.controller_did_lose_discovery(self, discovery_id)

# Device successfully paired and connected (also call on reconnect after reboot)
await self.dependencies.output.controller_did_connect_device(self, device_id)

# Device reported new parameter values or events
await self.dependencies.output.controller_did_receive_events(self, events)

# A user-facing problem — a CTA, or (still_running=False) a failure that leaves the
# integration inactive. Plain language for the user; technical detail goes to the logs.
await self.dependencies.output.controller_did_encounter_error(
    self, "The Zigbee stick is unplugged — re-plug it and restart the integration", still_running=False
)
```

### `last_error`

Both `Discovery` and `Device` carry a `last_error: str | None` field. **The integration owns this field entirely** — the Hub only stores and exposes it.

| Situation | Action |
|---|---|
| Connection attempt fails | Set `last_error` to a human-readable message and call the appropriate output method (`controller_did_receive_discovery`, `controller_did_update_discovery`, etc.) |
| Device fetch or command fails | Set `discovery.last_error` / `device.last_error` accordingly |
| Error is resolved | Set `last_error = None` explicitly — the Hub never clears it automatically |

```python
# On failure — surface the error to the user
discovery.last_error = "Connection timed out"
await self.dependencies.output.controller_did_update_discovery(self, discovery)

# On recovery — clear it explicitly
discovery.last_error = None
await self.dependencies.output.controller_did_update_discovery(self, discovery)
```

`Device.last_error` is persisted in the database, so stale errors survive restarts. Make sure to clear it whenever your integration successfully recovers, otherwise the error remains visible until explicitly resolved.

The natural places to clear it depend on the error kind — for connection errors, clear on successful connection or successful fetch; for discovery errors, clear when the device re-appears or its advertisement updates successfully. In general: wherever you can confirm the condition that caused the error no longer holds, that's where the `None` assignment belongs.

`last_error` is not limited to connection failures — use it for any condition worth surfacing to the user: authentication failures, unsupported firmware versions, misconfiguration, rate limiting, or any other integration-level problem. If the user should see it, put it here.

### `controller_did_encounter_error`

`last_error` is *persistent per-device/discovery state* — a flag on one device that stays until you clear it. `controller_did_encounter_error` is complementary: a **one-off, user-facing notification**, and the way to report a **controller-level** problem that isn't tied to a single device.

```python
async def controller_did_encounter_error(
    self, message: str, still_running: bool,
): ...
```

- **`message`** — plain language for the user, never a traceback. Put technical detail in the logs; put here only what the user should see, and fold any call-to-action right into the text.
- **`still_running`** — `False` when the controller can no longer run. The Hub marks the integration **inactive** and tells the user it failed (and what to do, if actionable) — no technical dump. If the controller was running, the Hub then restarts it; when `start()` raises, it retries after 5, 30 and 120 seconds before it gives up. Use `True` for a problem you've handled and recovered from but still want the user to know about (e.g. a user-fixable misconfiguration).

#### Which one do I use?

There are three places an error can go. Pick by asking who it's for and how long it should stay:

| Surface | Use it for | How long it lives |
|---|---|---|
| `Device.last_error` / `Discovery.last_error` | a problem with one device | stays until *you* clear it |
| `controller_did_encounter_error` | the whole integration has a problem; `still_running=False` = it failed and stopped | one-off notification |
| logs (`logger.*`) | technical detail, for you the developer | log retention |

**What about a parameter failing?** Parameters don't have an error field, on purpose. If one
parameter fails (a rejected command, an unreadable value), tell the user at the *device* level
and name the parameter in the message: `device.last_error = "Brightness could not be set — the
device rejected the command"`. Status codes and tracebacks go to the logs.

Two habits:

- **User surfaces get plain language** — never a traceback or a protocol code.
- **One incident usually goes to two places**: a detailed log line for you, plus one user-facing
  surface. Logs-only is fine only when the user can't see or fix anything.

```python
# Recoverable, but the user must act:
await self.dependencies.output.controller_did_encounter_error(
    self, "Matter server unreachable — check that the matter-server add-on is running", still_running=True
)

# Fatal — the integration can't continue:
await self.dependencies.output.controller_did_encounter_error(
    self, "The Zigbee coordinator is not responding and the integration has stopped.", still_running=False
)
```

### The `discoveries` property

Return your current in-memory cache of unpaired, visible devices. The Hub polls this — do not trigger scanning here.

```python
@property
def discoveries(self) -> dict[UUID, Discovery]:
    return self._discoveries  # maintained elsewhere, e.g. in a discovery event callback
```

The `UUID` for a given physical device must remain stable as long as it is visible.

### `start_pairing_window(duration_sec, credentials=None)`

```python
async def start_pairing_window(self, duration_sec: int, credentials: ProvidedCredentials | None = None) -> None: ...
```

Optional. Override only if your protocol requires an explicit short-lived scan mode to surface new devices (e.g. Zigbee permit-join, BLE burst scan). Always-on discovery (mDNS, SSDP) does not need this. Default is a no-op.

`credentials` carries anything the user supplied when opening the window, before any device is discovered — e.g. a Z-Wave SmartStart QR code / DSK. It is `None` when the user gave none. The Hub relays it from `POST start_pairing_window` (target integration in the `integration` query parameter, credentials in the request body).

## Injected Dependencies

The Hub populates `self.dependencies` (see [`AbstractController.Dependencies`](https://github.com/MajorDom-Systems/integration-sdk/tree/master/majordom_integration_sdk/controller/abstract_controller.py)) before calling `start()`.

| Field | Type | Description |
|---|---|---|
| `output` | `ControllerOutput` | Callback object for pushing events to the Hub |
| `make_device_repository` | `Callable[[], AsyncContextManager[DeviceRepository]]` | Factory for the device repository |
| `zeroconf_discovery_service` | `ZeroconfDiscoveryService` | Shared mDNS/Zeroconf discovery service |
| `ssdp_discovery_service` | `SSDPDiscoveryService` | Shared SSDP discovery service |
| `ble_discovery_service` | `BLEDiscoveryService` | Shared BLE scanner service |
| `links` | `Mapping[str, Endpoint]` | What your `needs` are bound to, by family, e.g. `links["zigbee"].url`. An optional need that isn't bound is missing |
| `settings` | `BaseModel \| None` | The validated instance of your `settings` model; `None` when you declare none |
| `context` | `Context` | Hub-wide facts: `region` (radio region), `wifi` (the network to put Wi-Fi devices on), `thread_dataset` (the hub's Thread network, hex) |
| `services` | `ServiceControl` | Restarts one of your own `services`, see [below](#restarting-your-service-and-healing) |

Device paths, server URLs and options all arrive here. Don't read them from environment variables or config files.

### Class attributes

Declare what the controller connects to and what the user can set as class attributes. The Hub reads them off the class before it constructs the controller.

| Attribute | Type | Default | Meaning |
|---|---|---|---|
| `needs` | `Sequence[Need]` | `()` | Capabilities the controller connects to, e.g. `[Need("matter", ["matter-server-ws"])]`. Bound ones arrive in `dependencies.links` |
| `services` | `Sequence[Service]` | `()` | Containers the integration brings along, e.g. Matter's `matterjs-server`. The Hub runs one only while something uses it |
| `settings` | `type[BaseModel] \| None` | `None` | Options the user can set, as a pydantic model. The validated instance arrives in `dependencies.settings` |

```python
from majordom_integration_sdk import Need

class ZigBeeController(AbstractController):
    needs = [Need("zigbee", ZIGPY_DIALECTS)]  # ezsp, znp, deconz, xbee, zigate, ziggurat, blz, cc
    settings = ZigBeeSettings

    async def start(self):
        link = self.dependencies.links["zigbee"]
        settings = cast(ZigBeeSettings, self.dependencies.settings or ZigBeeSettings())
        ...
```

An integration that only uses the network, like HomeKit, declares nothing. See [Connecting to Radios and Services](radios.md) and [Settings](settings.md).

### `probe(path)`

```python
@classmethod
async def probe(cls, path: str) -> Endpoint | None: ...
```

Optional. When the Hub finds a USB stick that none of its drivers recognise, it asks each integration whether the stick speaks one of its protocols. Return what the stick offers then, e.g. `Endpoint("zigbee", "znp", path)`, or `None`. The Hub remembers the answer, so it asks once per stick. An exception counts as `None`.

### `peripheral_did_change(change)`

```python
async def peripheral_did_change(self, change: PeripheralChange) -> bool: ...
```

Optional. Called while the controller runs, when one of its links appeared, moved, or an optional one was lost. `dependencies.links` already holds the new links. `change.family` names the link; `change.before` is `None` when it appeared, `change.after` is `None` when it was lost.

- Return `True` when you handled it in place. The controller keeps running.
- Return `False` (the default) to let the Hub restart the controller with the new links.

Links, settings and context can change at once. The Hub then calls every hook that applies, and restarts the controller unless all of them return `True`. A hook that raises counts as `False`. When a **required** link is lost, the Hub doesn't call this hook: it stops the controller, tells the user, and starts it again once the link is back.

```python
async def peripheral_did_change(self, change: PeripheralChange) -> bool:
    if change.family == "thread":  # an optional need: Wi-Fi devices keep working without it
        self._border_router = change.after.url if change.after else None
        return True
    return False
```

### `settings_did_change(before)`

```python
async def settings_did_change(self, before: BaseModel | None) -> bool: ...
```

Optional. Called while the controller runs, when the user changed its [settings](settings.md). `dependencies.settings` already holds the new ones, `before` the old ones.

Return `True` when applied in place; the default (`False`) has the Hub restart the integration.

Apply what's cheap to apply, and restart for the rest:

```python
class AcmeSettings(BaseModel):
    poll_interval: int = Field(30, ge=5, title="Refresh every, seconds")
    channel: int = Field(15, ge=11, le=26, title="Channel")


async def settings_did_change(self, before: BaseModel | None) -> bool:
    before = cast(AcmeSettings, before or AcmeSettings())
    settings = cast(AcmeSettings, self.dependencies.settings or AcmeSettings())
    if settings.channel != before.channel:
        return False  # start() forms the network on the channel: restart
    self._poll_interval = settings.poll_interval  # the poll loop reads it on its next round
    return True
```

### `context_did_change(before)`

```python
async def context_did_change(self, before: Context) -> bool: ...
```

Optional. Called while the controller runs, when [hub-wide facts](settings.md#hub-settings) changed: the radio region, the Wi-Fi network for new devices, the Thread network. `dependencies.context` already holds the new ones, `before` the old ones. Return `True` when applied in place; the default (`False`) has the Hub restart the integration.

```python
async def context_did_change(self, before: Context) -> bool:
    if self.dependencies.context.region != before.region:
        return False  # start() sets the radio's region: restart
    return True  # Wi-Fi and Thread are read from dependencies.context when pairing
```

### Restarting your service and healing

```python
class ServiceControl(Protocol):
    async def restart(self, service: str) -> None: ...
```

`dependencies.services.restart(name)` restarts one of the [services](radios.md#bringing-your-own-service) your integration brings, by its name, e.g. when the server reads a setting only at start. You can't restart another integration's service, or one the user runs. Without the Hub, in [standalone mode](standalone.md), it raises `NotImplementedError`: restart the server yourself.

```python
async def settings_did_change(self, before: BaseModel | None) -> bool:
    before = cast(AcmeSettings, before or AcmeSettings())
    settings = cast(AcmeSettings, self.dependencies.settings or AcmeSettings())
    if settings.log_level != before.log_level:
        await self._client.set_log_level(settings.log_level)  # the server applies it at start
        await self.dependencies.services.restart("acme-server")
    return True  # the connection drops, and _stay_connected() heals it
```

The integration keeps running while its service restarts, and nobody tells it the service is back: the Hub restarts the container, not the integration. The same happens when the server crashes and comes back. So don't let one connection live as long as the controller. Keep a task that waits for the connection to drop and reconnects with backoff, as the Matter integration does with matter-server ([`controller.py`](https://github.com/MajorDom-Systems/integration-matter/tree/master/majordom_matter/controller.py)):

```python
_RECONNECT_DELAY, _RECONNECT_DELAY_MAX = 1, 30  # seconds


async def start(self):
    self._client = await self._connect()  # raising here has the Hub retry start()
    self._keeper = asyncio.create_task(self._stay_connected())


async def stop(self):
    self._keeper.cancel()
    await self._client.close()


async def _connect(self) -> AcmeClient:
    client = AcmeClient(self.dependencies.links["acme"].url)
    await client.connect()
    return client


async def _stay_connected(self):
    """Reconnects whenever the server goes away, until stop() cancels it."""
    while True:
        await self._client.wait_closed()
        message = "Lost the connection to the Acme server, reconnecting."
        await self.dependencies.output.controller_did_encounter_error(self, message, still_running=True)
        delay = self._RECONNECT_DELAY
        while True:
            await asyncio.sleep(delay)  # 1, 2, 4, … 30, 30 seconds
            try:
                self._client = await self._connect()
                break
            except OSError as error:
                logger.info(f"The Acme server is not back yet: {error!r}")
                delay = min(delay * 2, self._RECONNECT_DELAY_MAX)
```

`still_running=True` tells the user the integration is degraded, not failed. While the connection is down, report the devices you reach through it as lost, and as connected again once it's back.

## Helper Methods

`AbstractController` provides these `@final` helpers. Do not override them. 

```python
@property
def name_slug(self) -> str: ...
# URL-safe slug of self.name; stable integration identifier

def integration_uuid(self) -> UUID: ...
# Stable UUID for this integration, derived from name_slug

def device_uuid(self, device_id: str) -> UUID: ...
# Stable UUID for a device given any unique string (MAC, serial, etc.)

def parameter_uuid(self, device_uuid: UUID, parameter_id: str) -> UUID: ...
# Stable UUID for a parameter scoped to its device

@property
def documents_folder(self) -> Path: ...
# Path to this integration's dedicated file storage directory
```

For example

```python
path = self.documents_folder / "zigbee.db"
```

Use the built-in uuid generators to make deterministic UUIDs — no DB lookup needed, IDs stay consistent across restarts and re-pairings. Discovery `id` isn't required to match Device `id`, but this is recommended.

```python
device_id = self.device_uuid(device_mac)
param_id = self.parameter_uuid(device_id, f"{accessory_id}.{characteristic_id}")
```

## See Also

- [`integration-template`](https://github.com/MajorDom-Systems/integration-template) — scaffold your repo with **Use this template**, then fill in the controller
- [Storing Data](storing_data.md) — `integration_data`, typed schemas, file storage, and the device repository
- [Data Models Reference](data_models.md) — `Discovery`, `Device`, `Parameter`, and related types
- [Example Integration](example-integration.md) — a full pseudo-code controller putting all of the above together, to copy as a starting point
