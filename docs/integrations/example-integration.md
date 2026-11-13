# Example Integration

This page is a **narrative walkthrough** of the example controller that ships in the
[`integration-template`](https://github.com/MajorDom-Systems/integration-template) repository.
The template is the source of truth for the actual, CI-verified code — start there with
**Use this template**, then read this page to understand *why* each piece looks the way it does.

The example isn't real protocol code — there's no such thing as "AcmeProtocol" or "AcmeClient".
Every piece that would normally come from a real device library is marked `# pseudo` so you know
it's made up. Everything else — module layout, method names, signatures, how the pieces call into
each other — matches the real SDK interfaces described in
[Implementing a Controller](controller.md), [Storing Data](storing_data.md), and
[Data Models Reference](data_models.md). Read this page *alongside* those, not instead of them.

If this is your first integration, don't worry about understanding every line the first time
through. Scaffold from the template, rename `Acme` to your protocol, and start replacing the
`# pseudo` bits with calls into your actual device library one at a time.

!!! tip "More examples"
    This page is a *pedagogical* walkthrough. For real, production integrations to learn from —
    HomeKit, Zigbee, Matter, and more — browse the official MajorDom integrations at
    [github.com/orgs/MajorDom-Systems/repositories?q=integration-](https://github.com/orgs/MajorDom-Systems/repositories?q=integration-).

## The controller at a glance

Before the details, here's the whole shape of a finished controller — every method you implement,
in one place. Bodies are elided (`...`); the sections group them by direction of data flow. If
you're new to OOP or SDKs, read this as the "table of contents" for the rest of the page.

```python
class MyController(AbstractController[MyDevice, MyParameter]):
    name = "My Protocol"  # optional — auto-derived from the class name otherwise

    # ── Lifecycle ────────────────────────────────────────────────────────────
    async def start(self) -> None: ...   # connect, start discovery, restore already-paired devices
    async def stop(self)  -> None: ...   # cancel tasks, stop discovery, close connections

    # ── Discovery  (Device → Hub) ────────────────────────────────────────────
    @property
    def discoveries(self) -> dict[UUID, Discovery]: ...   # cached snapshot of unpaired devices
    #   when a device appears, call:
    #     await self.output.controller_did_receive_discovery(self, discovery)

    # ── Pairing ──────────────────────────────────────────────────────────────
    async def start_pairing_window(self, duration_sec: int, credentials=None) -> None: ...  # optional (e.g. Zigbee)
    async def pair_device(self, discovery, draft, credentials) -> DeviceState: ...  # fill the draft: commission, identity only
    async def unpair(self, device: MyDevice) -> None: ...                  # also the rollback of a failed pairing

    # ── Control & read  (Hub → Device) ───────────────────────────────────────
    async def send_command(self, command, device, parameter) -> None: ...  # set a value / run command
    async def fetch(self, device: MyDevice) -> DeviceState | None: ...      # read the whole device + re-subscribe
    async def identify(self, device: MyDevice) -> None: ...                 # blink / beep the device

    # ── Events  (Device → Hub) ───────────────────────────────────────────────
    #   on an incoming device update, call:
    #     await self.output.controller_did_receive_events(self, [DeviceParameterChange(...)])
```

## Module Layout

Your integration is a standalone package (`majordom_<protocol>/`), scaffolded from the template:

```
majordom_acme/
├── __init__.py        # exports peripherals(platform): [AcmeController(platform)]
├── controller.py      # AbstractController subclass — the only file the Hub actually calls into
├── models.py          # typed integration_data schemas — what MajorDom persists to disk for you
└── mapper.py          # protocol <-> MajorDom conversions — pure functions, no I/O
```

## `models.py` — typed `integration_data`

`integration_data` is a free-form field MajorDom lets every integration attach to its own
`Device`/`Parameter` records, for protocol-specific bookkeeping (an auth token, an internal id,
etc.). Subclass the SDK schemas to give it a typed shape — the Hub then (de)serializes it for you.
Here we remember the device's network **hostname** (not IP — see the discovery note below) and an
auth token the Acme protocol handed us during pairing:

```python
from majordom_integration_sdk.schemas.base import Base
from majordom_integration_sdk.schemas.device import Device, DeviceState
from majordom_integration_sdk.schemas.parameter import Parameter, ParameterState

class AcmeDeviceIntegrationData(Base):
    device_hostname: str          # a hostname, resolved to the current IP by the OS
    auth_token: str | None = None

class AcmeParameterIntegrationData(Base):
    acme_property_name: str       # the name Acme's own API uses for this property

# Device/DeviceState and Parameter/ParameterState are pairs: the "State" version carries the
# same fields plus the actual live value(s). You need both — see Storing Data for why.
class AcmeDevice(Device):
    integration_data: AcmeDeviceIntegrationData

class AcmeDeviceState(DeviceState):
    integration_data: AcmeDeviceIntegrationData

class AcmeParameter(Parameter):
    integration_data: AcmeParameterIntegrationData

class AcmeParameterState(ParameterState):
    integration_data: AcmeParameterIntegrationData
```

To make the Hub hand you these subclasses (with `integration_data` already parsed), the controller
overrides `device_type`/`parameter_type` — see [Storing Data](storing_data.md#integration_data).

## `mapper.py` — pure conversions

Keep protocol↔domain conversions here: pure functions that turn "whatever your device library
gives you" into MajorDom's `Parameter`/`Device` types. No I/O, no `self.platform`, nothing that
touches the network or database — so you (or a test) can call them directly without a real device.
A property's `kind` maps to a `ParameterDataType`; whether it's `writable` maps to
`ParameterRole.control` vs `ParameterRole.sensor`:

```python
from majordom_integration_sdk.schemas.parameter import ParameterDataType, ParameterRole, ParameterVisibility
from .models import AcmeParameter, AcmeParameterIntegrationData

class AcmeMapper:
    def parameter_from_acme_property(self, parameter_id, acme_property: dict) -> AcmeParameter:
        data_type = ParameterDataType.bool if acme_property["kind"] == "bool" else ParameterDataType.integer
        role = ParameterRole.control if acme_property["writable"] else ParameterRole.sensor
        return AcmeParameter(
            id=parameter_id,
            name=acme_property["name"],
            data_type=data_type,
            role=role,
            visibility=ParameterVisibility.user,   # show on the device's main screen; see Data Models for setting/system
            integration_data=AcmeParameterIntegrationData(acme_property_name=acme_property["name"]),
        )
```

`device_uuid`/`parameter_uuid` are helpers on `AbstractController`
([Helper Methods](controller.md#helper-methods)) — call them from the controller and pass the
resulting ids into the mapper, since the mapper has no access to `self`.

## `controller.py` — the walkthrough

The package's `peripherals(platform)` builds the controller. It declares its identity as a **class
attribute** and subclasses the generic `AbstractController`:

```python
from majordom_integration_sdk import DeviceUnreachableError
from majordom_integration_sdk.capabilities import ZEROCONF
from majordom_integration_sdk.controller import AbstractController
from .models import AcmeDevice, AcmeParameter

class AcmeController(AbstractController[AcmeDevice, AcmeParameter]):
    name = "Acme"                 # shown to the user; its slug "acme" is the key
    needs = [ZEROCONF]  # Acme devices announce themselves over mDNS
    _mapper = AcmeMapper()        # stateless, so one shared instance is fine
```

### Lifecycle: `start` / `stop`

`start()` runs once its needs are bound (at boot, when enabled, after a restart); `stop()` on shutdown or before a restart.
Two things happen in `start()`: register for discovery (keep the returned **cancel closure** for
`stop`), and — crucially — **reconnect to already-paired devices**. On every Hub restart, `start()`
is your only chance to do that; skip it and paired devices look "stuck" until re-paired.
`controller_did_connect_device` isn't just for "just finished pairing" — call it any time a device
becomes reachable, including here at boot, to flip `device.available` back to `True`:

```python
async def start(self):
    self._discoveries = {}
    self._subscriptions = {}  # physical id -> cancel closure
    self._client = AcmeClient()  # pseudo
    self._cancel_discovery = self.peripherals.instance(ZEROCONF).register(self, {"_acme._tcp.local."})

    async with self.platform.device_repository(self) as repo:
        for device in await repo.get_all(as_=AcmeDevice):  # scoped to this integration's key
            self._subscribe(device)
            await self.output.controller_did_connect_device(self, physical_id=device.physical_id)

async def stop(self):
    self._cancel_discovery()
    await self._client.close()  # pseudo
```

### Discovery callbacks: identify by hostname, never by IP

Zeroconf (`self.peripherals.instance(ZEROCONF)`) calls three listener methods (`zeroconf_did_discover_service`,
`..._update_service`, `..._remove_service`) because you passed `self` to `register()`. Derive the
**stable** discovery id from `info.name` (the mDNS instance name), which stays constant across
discover/update/remove for the same physical device — **not** from its IP address:

> If you keyed the id off the IP, a routine DHCP lease renewal would change the address and the Hub
> would think a *brand-new* device appeared instead of recognizing the one it already knew. Storing
> a **hostname** in `integration_data` (rather than an IP) sidesteps this entirely: the OS resolves
> the hostname to the current IP for you, so a paired device changing IP requires no work at all. If
> you must store an IP, you'd have to update it *and* re-verify reachability on every update event.

`_update_service` only reports a device still in your `discoveries` dict (an unpaired device whose
advertisement changed); `_remove_service` gives you only `name`, so pop by the same derived id and
call `controller_did_lose_discovery`.

### `pair_device`: fill the draft

The Hub builds a **draft** from what the user entered (name, room, icon) and hands it to you with the discovery. You fill it in and return it. The Hub saves it, so you don't touch the repository and you report nothing about the device yet.

**Always validate** that the credentials actually sent match the discovery's advertised options — never trust your own discovery-time guess:

```python
async def pair_device(
    self, discovery: Discovery, draft: DeviceState, credentials: ProvidedCredentials | None
) -> DeviceState:
    if not credentials or credentials.type not in discovery.expected_credentials_options:
        raise ValueError("Unsupported or missing credentials for this discovery")

    serial = await self._client.read_serial(discovery.id)  # pseudo, read-only
    draft.physical_id = self.device_uuid(serial)  # your lookup id; draft.id is the Hub's, never change it
    await self.check_device_id(draft.physical_id, draft)  # raises DeviceIdTakenError: nothing irreversible ran yet
    ...
```

The device now has its `physical_id`, distinct from its (temporary) discovery id. Build it from the serial number, a string unique to that device. A name or an address two devices share would give them the same id. `check_device_id` raises `DeviceIdTakenError` when another record already holds the id, so the user gets a clear refusal and the device is left untouched.

Now the irreversible step. Write what it changes to `integration_data` **first**, then run it. If anything fails, the Hub calls `unpair(draft)`, which reads the draft to know what to undo. Pairing must also be idempotent: a retry may find the device as an earlier attempt left it, so reuse a key the draft already carries instead of refusing:

```python
    known = draft.integration_data.session_key if draft.integration_data else None  # pseudo: pairing onto a record
    key = known or new_session_key()  # pseudo
    draft.integration_data = AcmeDeviceIntegrationData(device_hostname=hostname, session_key=key)
    await self._client.pair(discovery.id, code=credentials.value, session_key=key)  # pseudo, irreversible; a no-op when already paired with this key

    draft.available = True
    return draft
```

Don't map parameters, call `_subscribe` or `controller_did_connect_device` here. The Hub saves the draft, reports the device connected, and then calls `fetch`, which reads the parameters and subscribes.

### `unpair`: also the rollback

`unpair` tells the device to forget the pairing (the Hub removes its own record). It is also what the Hub calls to roll back a failed pairing, or one it failed to save, with the draft as you left it. So it must cope with a draft at any stage (no `integration_data`, a device already reset), undo everything pairing did in reverse order, never wait for the user, and be safe to call again. It talks to the device only: when the device can't be reached, raise `DeviceUnreachableError` and change nothing else. The app then offers the user to forget the device, which only the Hub does.

```python
async def unpair(self, device: AcmeDevice):
    data = device.integration_data
    if data is None:  # pair_device failed before the irreversible step: nothing to undo
        return
    self._unsubscribe(device)  # stop listening; a no-op when not subscribed
    try:
        await self._client.forget(data.device_hostname, session_key=data.session_key)  # pseudo; a no-op when already forgotten
    except AcmeError as error:  # pseudo: the device is gone
        raise DeviceUnreachableError(f"{device.physical_id} is unreachable") from error
```

### `identify` / `fetch`

Thin wrappers over your client: `identify` makes the device blink/beep so the user can find it.

`fetch` reads the whole device, and it is safe to call any number of times. It reads every parameter with its current value and returns the device with them, without saving anything: the Hub stores them and tells the app what changed. It checks the subscription and subscribes again only if it is gone, never twice. A sleeping battery device that doesn't answer returns `None`: not a failure.

```python
async def fetch(self, device: AcmeDevice) -> AcmeDeviceState | None:
    try:
        properties = await asyncio.wait_for(self._client.get_properties(device.integration_data.device_hostname), 10)  # pseudo
    except TimeoutError:
        return None
    if device.physical_id not in self._subscriptions:
        self._subscribe(device)
    parameters = self._mapper.parameters(self, device.physical_id, properties)  # pseudo: with their current values
    return AcmeDeviceState(**device.model_dump(), parameters=parameters, available=True)
```

### `send_command`: Hub → device

Called when the user changes something in the app. `command.value` is the new value; `parameter`
tells you which property — look up the protocol's own name from your `integration_data`:

```python
async def send_command(self, command: DeviceCommand, device: AcmeDevice, parameter: AcmeParameter):
    await self._client.set_property(
        device.integration_data.device_hostname,
        parameter.integration_data.acme_property_name,
        command.value,
    )  # pseudo
```

### `_subscribe`: device → Hub

Called once per device — from `fetch` after pairing and once per already-paired device at boot. Whenever the
device's own state changes, report it. Because protocol callbacks are usually plain (non-async), you
schedule the async report as a task:

```python
from majordom_integration_sdk.schemas.event import DeviceParameterChange

def _subscribe(self, device: AcmeDevice):
    def on_property_changed(acme_property_name: str, value):
        event = DeviceParameterChange(
            physical_id=device.physical_id,
            parameter_id=self.parameter_uuid(device.physical_id, acme_property_name),
            value=value,
        )
        asyncio.create_task(self.output.controller_did_receive_events(self, [event]))

    def on_availability_changed(is_available: bool):
        # Optional mid-session availability: report only if your protocol can detect a *paired*
        # device dropping/returning while the Hub runs. If it can't, omit this entirely.
        cb = (self.output.controller_did_connect_device if is_available
              else self.output.controller_did_lose_device)
        asyncio.create_task(cb(self, physical_id=device.physical_id))

    self._subscriptions[device.physical_id] = self._client.subscribe(
        device.integration_data.device_hostname,
        on_property_changed=on_property_changed,
        on_availability_changed=on_availability_changed,
    )  # pseudo: returns a cancel closure; `_unsubscribe` pops it and calls it
```

## What's Deliberately Left Out

The example skips a few things your real integration will likely need, so it doesn't obscure the
shape of the interface itself:

- **Error handling** — set `discovery.last_error` / `device.last_error` on failures (see
  [Implementing a Controller: `last_error`](controller.md#last_error)).
- **`start_pairing_window`** — only implement it if your protocol needs an explicit, short-lived
  scan mode (Zigbee permit-join, BLE burst scan). Always-on discovery (mDNS, SSDP) doesn't need it.
- **Retry/backoff, connection pooling, rate limiting** — whatever your protocol's client needs; the
  SDK prescribes nothing here.
- **Implementing the protocol yourself** — the example assumes `AcmeClient` already exists as a
  high-level SDK (`pair`, `get_properties`, `set_property`, ...). Real protocols don't always have
  one; if yours doesn't, you may implement the transport, connection management, and serialization
  directly inside your integration. That's expected. The framework (`AbstractController`, the
  discovery peripherals, the `Device`/`Parameter` models) is deliberately independent of any protocol's
  implementation details — and, the discovery providers and data models in particular being plain public
  SDK, can be reused standalone (e.g. to build a protocol library outside MajorDom entirely).

## Testing

Test your controller against simulated devices with the SDK's `majordom_integration_sdk.testing`
doubles — `build_test_platform()` plus `RecordingControllerOutput`, and `FakeZeroconf` for the `ZEROCONF` need — rather than real hardware.
See [Testing](index.md#testing) and the template's own `tests/` for the pattern.
