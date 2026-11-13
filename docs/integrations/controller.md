# Implementing a Controller

!!! tip "Start from the template"
    Scaffold your integration from the
    [`integration-template`](https://github.com/MajorDom-Systems/integration-template)
    (**Use this template → Create a new repository**), and read the
    [Example Integration](example-integration.md) walkthrough alongside this page — it puts every
    piece below together in one worked controller.

## AbstractController Overview

Your integration's controller subclasses [`AbstractController`](https://github.com/MajorDom-Systems/integration-sdk/tree/develop/majordom_integration_sdk/controller/abstract_controller.py) from the SDK. It is generic over your `Device` and `Parameter` subclasses, your [settings](settings.md) model, and the model of the draft a pairing fills (the last two are optional):

```python
from majordom_integration_sdk.controller import AbstractController
from majordom_integration_sdk.schemas import Device, Parameter

class MyController(AbstractController[Device, Parameter]):
    name = "My Protocol"  # optional — auto-derived from the class name ("My") otherwise
    ...
```

The full form is `AbstractController[TDevice, TParameter, TSettings, TDeviceState]`. `TSettings` defaults to `Any` and `TDeviceState` to `DeviceState`. To type the draft, write `Any` in the settings slot if you have none, and override `device_state_type` (see [Storing Data](storing_data.md#integration_data)).

### The `name` and `key` identity

`name` is a **class attribute**, shown to the user. It defaults to the class name without `Controller` (`HueController` → `"Hue"`):

```python
class MyController(AbstractController[Device, Parameter]):
    name = "Hue"
```

Its slug is the controller's `key` (`"hue"`). The Hub knows the integration by its key: its devices (`Device.integration`), settings, documents folder, `DISABLE_SERVICES` and `/integrations/{key}/…`. Never rename `name` once released.

### The entry point

The integration package exports `peripherals(platform)`: the controller and the services it brings along. The Hub calls it with its `Platform`.

```python
def peripherals(platform: Platform) -> list[Peripheral]:
    return [matterjs_server(), MatterController(platform)]
```

### Hub → Device

Implement all abstract methods defined in [`AbstractController`](https://github.com/MajorDom-Systems/integration-sdk/tree/develop/majordom_integration_sdk/controller/abstract_controller.py) — `start`, `stop`, `pair_device`, `unpair`, `identify`, `fetch`, `send_command`, and the `discoveries` property. The Hub calls these to drive your integration.

### Pairing

The Hub pairs a device in two steps: your `pair_device` fills a **draft**, then the Hub saves it. No device record exists while `pair_device` runs.

```python
async def pair_device(
    self, discovery: Discovery, draft: DeviceState, credentials: ProvidedCredentials | None
) -> DeviceState: ...
```

The Hub builds `draft` from what the user entered in the app: name, room, icon, category, note. Its `id` is the Hub's own and read-only: never change it. Its `physical_id` holds the discovery's id as a placeholder, and `integration` is your key. When the user picks an existing record to pair onto, the draft carries that record's data instead, its `id`, `physical_id` and `integration_data` included. The integration decides what in it is stale.

You establish the device's identity and trust only: its `physical_id`, `integration_data` (keys, addresses), `available`. Then you return the draft. The Hub saves it, reports the device connected if it is `available`, and calls `fetch`, which gives the device its parameters. So, during `pair_device`:

- **Don't use the device repository.** Nothing is saved while pairing.
- **Report nothing about this device.** No `controller_did_connect_device`, no events. The Hub reports after it saved the draft.
- **Check the physical id early.** As soon as you know it, call `check_device_id` (below), before anything irreversible: it confirms no other record holds this device already.
- **Fill `integration_data` before each irreversible step.** A key you are about to set, a node you are about to include: write it to the draft first. It is saved with the device, so you need no storage of your own. If pairing fails, the Hub calls `unpair(draft)` to roll back, and `unpair` can only undo what the draft says ran.
- **Just raise on failure.** The Hub's `unpair(draft)` undoes the partial pairing.
- **Don't map parameters, read values or subscribe.** Leave `parameters` empty: the Hub calls `fetch` for all of that right after the save.
- **Be idempotent.** The user may retry after a failed or rolled-back attempt, with a fresh draft. Bring the device to a known-good paired state from whatever the last attempt left: check each step and redo only what is missing or stale. A device found already paired is confirmed and returned, not refused.
- **Raise when you can't pair.** Raise `MissingCredentialsError` before touching the device when the Hub lacks credentials.

```python
async def pair_device(self, discovery, draft, credentials):
    if not discovery.accepts(credentials):
        raise ValueError("Unsupported or missing credentials for this discovery")
    serial = await self._client.read_serial(discovery.id)                   # pseudo, read-only
    draft.physical_id = self.device_uuid(serial)
    await self.check_device_id(draft.physical_id, draft)                    # before anything irreversible
    draft.integration_data = AcmeDeviceIntegrationData(device_key=new_key)  # before the step it describes
    await self._client.pair(discovery.id, key=new_key)                      # pseudo, irreversible
    draft.available = True
    return draft
```

#### `check_device_id`

```python
@final
async def check_device_id(self, physical_id: UUID, draft: TDeviceState): ...
```

Optional, but call it. It raises `DeviceIdTakenError` when another record holds `physical_id`, the one you are giving the device. The record the user picked to pair onto (`draft.id`) is not another. The Hub refuses the pairing with that error and does not roll it back, because nothing ran.

```python
from majordom_integration_sdk.errors import DeviceIdTakenError

error: DeviceIdTakenError
error.physical_id # the id in question
error.device_id   # the Hub id of the record that holds it
error.name        # the name of the record that holds it
error.is_paired   # False: a record kept after its device was removed
```

The app uses the record's name and `is_paired` to offer pairing onto that record instead.

#### Device ids

A device has two ids:

- `id` is the Hub's. The Hub assigns it, and you never change it.
- `physical_id` is yours: what you look the device up by, in the repository (`repo.get(physical_id=...)`), in events and in `controller_did_connect_device(self, physical_id=...)`. Build it with `device_uuid(s)`, where `s` is a string or bytes unique to that device: a MAC address or a serial number. Build it in one place, a single id-making method, never assembled anew at each call site. A name or an address two devices share gives them the same id, and the second one can't be paired. Never change the `physical_id` of a device that is already paired.

#### `unpair` is also the rollback

```python
async def unpair(self, device: TDevice): ...
```

The user triggers it to remove a device. The Hub also calls it to roll back, with the draft as `pair_device` left it, at any stage: when `pair_device` raises anything but `DeviceIdTakenError`, and when the Hub fails to save what it returned. So:

- Undo everything pairing did, in reverse order: a key set on the device, the pairing it holds, its place on the network or fabric.
- Tolerate any partial state: a placeholder `physical_id`, no `integration_data`, a device already reset.
- Never wait for the user. Go as far as you can: it is best effort, and the Hub cuts it off after 30 seconds.
- Make it safe to call again. On a device already unpaired, or never fully paired, it does nothing more.

Talk to the device only: the Hub alone decides whether to delete the record and its `integration_data`. When the device can't be reached, raise `DeviceUnreachableError` and change nothing else.

The user sees the original pairing error, not an error from the rollback. When the rollback can't reach the device, the Hub answers `pairing_failed`: "Pairing failed. The device may need a manual factory reset to pair again."

#### Removing a device

The app removes a device with `DELETE /device/{id}?mode=...`:

| `mode` | What happens |
|---|---|
| `unpair` | calls `unpair`, keeps the record |
| `delete` (default) | calls `unpair`, then removes the record |
| `forget` | removes the record without calling `unpair` |

When `unpair` raises `DeviceUnreachableError`, the Hub answers 409 `device_unreachable`: "Device unreachable. Forget it instead? It might need a manual factory reset to pair again."

#### `fetch` reads the whole device

```python
async def fetch(self, device: TDevice) -> TDeviceState | None: ...
```

The Hub calls it right after pairing, on a manual refresh, and to revive a device that is unavailable. It is idempotent:

- Read the whole device and return it: `device` with its full `parameters` list (ids from `parameter_uuid`, current values) and `available`. The Hub creates the parameters on the first fetch, then compares each one with what it stored: new and gone parameters, changed values. The Hub saves it. Report none of it as events: those are for changes the device starts itself.
- Check its event subscription. Subscribe again only if it is gone. Never create a second one.
- Finish in bounded time. Return `None` when the device doesn't answer, like a sleeping battery device: it is not a failure, and the Hub keeps what it has.

### Device → Hub

Use `self.output` (a `ControllerOutput`), injected by the Hub:

```python
# New unpaired device found during discovery
await self.output.controller_did_receive_discovery(self, discovery)

# An already-discovered (unpaired) device changed its advertisement
await self.output.controller_did_update_discovery(self, discovery)

# A previously-discovered device is no longer visible
await self.output.controller_did_lose_discovery(self, discovery_id)

# Device connected; on start, report every paired device that answers.
# Never during pair_device: the Hub reports a new device itself once it saved it.
# Ids are keyword-only: pass physical_id= (device_id= is for relays passing on the Hub's id)
await self.output.controller_did_connect_device(self, physical_id=physical_id)

# A paired device became unreachable while the Hub is running
await self.output.controller_did_lose_device(self, physical_id=physical_id)

# Device reported new parameter values or events; the Hub saves their values
await self.output.controller_did_receive_events(self, events)

# A user-facing problem with the whole integration — a CTA, or (is_still_running=False) a failure
# that leaves it inactive. Plain language for the user; technical detail goes to the logs.
await self.output.controller_did_encounter_error(
    self, IntegrationError("server-unreachable", "The Acme server is unreachable — check that it is running")
)

# The problem is gone
await self.output.controller_did_resolve_error(self, "server-unreachable")
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
await self.output.controller_did_update_discovery(self, discovery)

# On recovery — clear it explicitly
discovery.last_error = None
await self.output.controller_did_update_discovery(self, discovery)
```

`Device.last_error` is persisted in the database, so stale errors survive restarts. Make sure to clear it whenever your integration successfully recovers, otherwise the error remains visible until explicitly resolved.

The natural places to clear it depend on the error kind — for connection errors, clear on successful connection or successful fetch; for discovery errors, clear when the device re-appears or its advertisement updates successfully. In general: wherever you can confirm the condition that caused the error no longer holds, that's where the `None` assignment belongs.

`last_error` is not limited to connection failures — use it for any condition worth surfacing to the user: authentication failures, unsupported firmware versions, misconfiguration, rate limiting, or any other integration-level problem. If the user should see it, put it here.

### `controller_did_encounter_error`

`last_error` is *persistent per-device/discovery state* — a flag on one device that stays until you clear it. `controller_did_encounter_error` is complementary: the way to report a **controller-level** problem that isn't tied to a single device. The problem stays active until you resolve it, or until the integration stops or restarts.

```python
@dataclass(frozen=True)
class IntegrationError:  # from majordom_integration_sdk import IntegrationError
    id: str
    message: str
    is_still_running: bool = True


async def controller_did_encounter_error(self, controller, error: IntegrationError) -> None: ...
async def controller_did_resolve_error(self, controller, error_id: str) -> None: ...
```

- **`id`** — stable per condition, e.g. `"server-unreachable"` or `"stick-unplugged"`: it links the report to its resolve. Reporting an active id again replaces it, so you can report on every failed attempt without piling up duplicates. Several ids can be active at once. Ids are scoped to your integration (the Hub and the app key an error by integration and id), and the `hub-` prefix is reserved for the errors the Hub reports on an integration's behalf.
- **`message`** — plain language for the user, never a traceback. Put technical detail in the logs; put here only what the user should see, and fold any call-to-action right into the text.
- **`is_still_running`** — `False` when the controller can no longer run. The Hub marks the integration **inactive** and tells the user it failed (and what to do, if actionable) — no technical dump. If the controller was running, the Hub then restarts it; when `start()` raises, it retries after 5, 30 and 120 seconds before it gives up. Keep the default `True` for a problem the integration keeps running through but the user should know about (a lost server it reconnects to, a user-fixable misconfiguration).

Call `controller_did_resolve_error` with the id once the condition no longer holds: the connection is back, the user fixed the setup. Resolving an id that isn't active does nothing, so you can resolve after every successful connection. The Hub keeps active errors in memory only (they are not saved) and drops all of an integration's errors when it stops or restarts, so a `is_still_running=False` error is gone once the Hub restarts the integration.

#### Which one do I use?

There are five places an error can go. Pick by asking who it's for and how long it should stay:

| Surface | Use it for | How long it lives |
|---|---|---|
| `Device.last_error` / `Discovery.last_error` | a problem with one device | stays until *you* clear it |
| `controller_did_encounter_error` | the whole integration has a problem; `is_still_running=False` = it failed and stopped | until resolved, or the integration restarts |
| `DeviceIdTakenError` raised by `check_device_id` | another record already holds the id this pairing would give; see [Device ids](#device-ids) | returned to the app with this pairing attempt |
| `DeviceUnreachableError` raised by `unpair` | the device can't be reached to undo its pairing; see [`unpair`](#unpair-is-also-the-rollback) | returned to the app, which offers to forget the device |
| `MissingCredentialsError` raised from `pair_device` | the Hub lacks credentials (e.g. Wi-Fi) for one pairing; see [Missing Hub credentials](data_models.md#missing-hub-credentials) | returned to the app with this pairing attempt |
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
# Recoverable, but the user must act; reported on every failed attempt, it stays one error:
await self.output.controller_did_encounter_error(
    self, IntegrationError("server-unreachable", "Matter server unreachable — check that it is running")
)

# ... and once connected again:
await self.output.controller_did_resolve_error(self, "server-unreachable")

# Fatal — the integration can't continue (the Hub restarts it, which clears the error):
await self.output.controller_did_encounter_error(
    self,
    IntegrationError("radio-lost", "The Zigbee coordinator is not responding and the integration has stopped.", False),
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

## What the Hub Gives

A controller is a [`Peripheral`](peripherals.md). It is constructed as `Controller(platform, settings=None)`; keep these parameters when you override `__init__`. The runtime sets the rest before `start()`.

| Attribute | Type | Description |
|---|---|---|
| `self.platform` | `Platform` | The host, frozen and shared by every peripheral: `region`, `wifi`, `thread_dataset`, `documents_folder(self)`, `device_repository(self)` |
| `self.output` | `ControllerOutput` | What it reports to the Hub; logs every call in library mode |
| `self.settings` | your `Settings` | The validated [settings](settings.md); `NoSettings` when you declare none |
| `self.peripherals` | `Peripherals` | What your `needs` are bound to, by family |

| Call | Returns |
|---|---|
| `self.peripherals.endpoint("zigbee")` | the `Endpoint` bound to that need; `KeyError` while it is unbound |
| `self.peripherals.endpoints("ble")` | every endpoint bound to an `is_many` need, as a list; empty while unbound |
| `self.peripherals.instance(BLE_ROUTER)` | the in-process peripheral bound to a typed need (`BLE_ROUTER`, `ZEROCONF`, `UPNP_SSDP`), typed by it; `None` while unbound |

Device paths, server URLs, discovery and options all arrive here. Don't read them from environment variables or config files, and don't start your own mDNS, SSDP or Bluetooth stack. Read `self.platform` when you need a fact: a platform you kept holds the old ones.

### Needs and settings

`needs` is a class attribute: everything external the controller uses. Settings are a nested `Settings` model, named as the last type parameter.

```python
from majordom_integration_sdk import Need

class ZigBeeController(AbstractController[Device, Parameter, "ZigBeeController.Settings"]):
    needs = [Need("zigbee", ZIGPY_DIALECTS)]  # ezsp, znp, deconz, xbee, zigate, ziggurat, blz, cc

    class Settings(BaseModel):
        channel: int = Field(15, ge=11, le=26, title="Channel")

    async def start(self):
        link = self.peripherals.endpoint("zigbee")
        channel = self.settings.channel
        ...
```

HomeKit, which only uses the network, needs just `ZEROCONF`. Make a typed need optional with `dataclasses.replace(BLE_ROUTER, is_required=False)`. See [Peripherals](peripherals.md) and [Settings](settings.md).

### Hooks

Each hook is optional and called while the controller runs. Return `True` when you handled the change in place; `False` has the runtime restart the controller. Several can fire at once: the controller restarts unless all return `True`. A hook that raises counts as `False`.

| Hook | Called when | Default |
|---|---|---|
| `needed_peripheral_did_change(change)` | a bound need appeared, moved, or an optional one was lost; `self.peripherals` holds the new binding | `False` |
| `settings_did_change(before)` | the user changed its settings; `self.settings` holds the new ones | `False` |
| `platform_facts_did_change(before)` | region, Wi-Fi or Thread network changed; `self.platform` holds the new ones | `True` |

When a **required** need is lost, no hook is called: the runtime stops the controller and starts it again once the need is bound.

```python
async def needed_peripheral_did_change(self, change: PeripheralChange) -> bool:
    if change.family == "thread":  # optional: Wi-Fi devices keep working without it
        self._border_router = change.after.url if change.after else None
        return True
    return False


async def settings_did_change(self, before: Settings) -> bool:
    if self.settings.channel != before.channel:
        return False  # start() forms the network on the channel: restart
    return True


async def platform_facts_did_change(self, before: Platform) -> bool:
    return self.platform.region == before.region  # start() sets the radio's region
```

### Staying connected

A [service](peripherals.md#tldr-bringing-a-docker-service) is recreated when its settings or bindings render it differently, and it may crash and come back. Nobody tells the controller. So don't let one connection live as long as the controller: keep a task that waits for the connection to drop and reconnects with backoff.

```python
async def _stay_connected(self):
    """Reconnects whenever the server goes away, until stop() cancels it."""
    while True:
        await self._client.wait_closed()
        message = "Lost the connection to the Acme server, reconnecting."
        await self.output.controller_did_encounter_error(self, IntegrationError("server-unreachable", message))
        delay = self._RECONNECT_DELAY
        while True:
            await asyncio.sleep(delay)  # 1, 2, 4, … 30, 30 seconds
            try:
                self._client = await self._connect()
                break
            except OSError as error:
                logger.info(f"The Acme server is not back yet: {error!r}")
                delay = min(delay * 2, self._RECONNECT_DELAY_MAX)
        await self.output.controller_did_resolve_error(self, "server-unreachable")
```

`is_still_running=True` (the default) tells the user the integration is degraded, not failed, until the error is resolved. Resolve it only once a connection held for `STABLE_RUN` seconds, so a server that answers and drops every time is still reported. While the connection is down, report the devices you reach through it as lost, and as connected again once it's back.

## Helper Methods

`AbstractController` provides these `@final` helpers. Do not override them. 

```python
@property
def key(self) -> str: ...
# slug of name; the stable integration identifier

def integration_uuid(self) -> UUID: ...
# Stable UUID for this integration, derived from key

def device_uuid(self, raw: str | bytes) -> UUID: ...
# The physical_id of a device from a string unique to it (MAC, serial); devices sharing the string share the id

async def check_device_id(self, physical_id: UUID, draft: TDeviceState): ...
# Raises DeviceIdTakenError when another record holds the physical id; call it from pair_device

def parameter_uuid(self, physical_id: UUID, raw: str | bytes) -> UUID: ...
# Stable UUID for a parameter, scoped to its device's physical_id
```

## See Also

- [`integration-template`](https://github.com/MajorDom-Systems/integration-template) — scaffold your repo with **Use this template**, then fill in the controller
- [Storing Data](storing_data.md) — `integration_data`, typed schemas, file storage, and the device repository
- [Data Models Reference](data_models.md) — `Discovery`, `Device`, `Parameter`, and related types
- [Example Integration](example-integration.md) — a full pseudo-code controller putting all of the above together, to copy as a starting point
