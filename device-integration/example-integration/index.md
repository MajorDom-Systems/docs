# Example Integration

This page is a **narrative walkthrough** of the example controller that ships in the [`integration-template`](https://github.com/MajorDom-Systems/integration-template) repository. The template is the source of truth for the actual, CI-verified code — start there with **Use this template**, then read this page to understand *why* each piece looks the way it does.

The example isn't real protocol code — there's no such thing as "AcmeProtocol" or "AcmeClient". Every piece that would normally come from a real device library is marked `# pseudo` so you know it's made up. Everything else — module layout, method names, signatures, how the pieces call into each other — matches the real SDK interfaces described in [Implementing a Controller](https://docs.majordom.io/device-integration/controller/index.md), [Storing Data](https://docs.majordom.io/device-integration/storing_data/index.md), and [Data Models Reference](https://docs.majordom.io/device-integration/data_models/index.md). Read this page *alongside* those, not instead of them.

If this is your first integration, don't worry about understanding every line the first time through. Scaffold from the template, rename `Acme` to your protocol, and start replacing the `# pseudo` bits with calls into your actual device library one at a time.

More examples

This page is a *pedagogical* walkthrough. For real, production integrations to learn from — HomeKit, Zigbee, Matter, and more — browse the official MajorDom integrations at [github.com/orgs/MajorDom-Systems/repositories?q=integration-](https://github.com/orgs/MajorDom-Systems/repositories?q=integration-).

## The controller at a glance

Before the details, here's the whole shape of a finished controller — every method you implement, in one place. Bodies are elided (`...`); the sections group them by direction of data flow. If you're new to OOP or SDKs, read this as the "table of contents" for the rest of the page.

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
    #     await self.dependencies.output.controller_did_receive_discovery(self, discovery)

    # ── Pairing ──────────────────────────────────────────────────────────────
    async def start_pairing_window(self, duration_sec: int) -> None: ...  # optional (e.g. Zigbee)
    async def pair_device(self, discovery, credentials) -> UUID: ...       # commission + map schema
    async def unpair(self, device: MyDevice) -> None: ...

    # ── Control & read  (Hub → Device) ───────────────────────────────────────
    async def send_command(self, command, device, parameter) -> None: ...  # set a value / run command
    async def fetch(self, device: MyDevice) -> None: ...                    # re-read all parameters
    async def identify(self, device: MyDevice) -> None: ...                 # blink / beep the device

    # ── Events  (Device → Hub) ───────────────────────────────────────────────
    #   on an incoming device update, call:
    #     await self.dependencies.output.controller_did_receive_events(self, [DeviceParameterChange(...)])
```

## Module Layout

Your integration is a standalone package (`majordom_<protocol>/`), scaffolded from the template:

```text
majordom_acme/
├── __init__.py        # exports AcmeController
├── controller.py      # AbstractController subclass — the only file the Hub actually calls into
├── models.py          # typed integration_data schemas — what MajorDom persists to disk for you
└── mapper.py          # protocol <-> MajorDom conversions — pure functions, no I/O
```

## `models.py` — typed `integration_data`

`integration_data` is a free-form field MajorDom lets every integration attach to its own `Device`/`Parameter` records, for protocol-specific bookkeeping (an auth token, an internal id, etc.). Subclass the SDK schemas to give it a typed shape — the Hub then (de)serializes it for you. Here we remember the device's network **hostname** (not IP — see the discovery note below) and an auth token the Acme protocol handed us during pairing:

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

To make the Hub hand you these subclasses (with `integration_data` already parsed), the controller overrides `device_type`/`parameter_type` — see [Storing Data](https://docs.majordom.io/device-integration/storing_data/#integration_data).

## `mapper.py` — pure conversions

Keep protocol↔domain conversions here: pure functions that turn "whatever your device library gives you" into MajorDom's `Parameter`/`Device` types. No I/O, no `self.dependencies`, nothing that touches the network or database — so you (or a test) can call them directly without a real device. A property's `kind` maps to a `ParameterDataType`; whether it's `writable` maps to `ParameterRole.control` vs `ParameterRole.sensor`:

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

`device_uuid`/`parameter_uuid` are helpers on `AbstractController` ([Helper Methods](https://docs.majordom.io/device-integration/controller/#helper-methods)) — call them from the controller and pass the resulting ids into the mapper, since the mapper has no access to `self`.

## `controller.py` — the walkthrough

The controller is the only file the Hub instantiates. It declares its identity as a **class attribute** and subclasses the generic `AbstractController`:

```python
from majordom_integration_sdk.controller import AbstractController
from .models import AcmeDevice, AcmeParameter

class AcmeController(AbstractController[AcmeDevice, AcmeParameter]):
    name = "Acme"                 # class-level identity — the Hub reads it before constructing you
    _mapper = AcmeMapper()        # stateless, so one shared instance is fine
```

### Lifecycle: `start` / `stop`

`start()` runs once when the Hub boots (or when the integration is enabled); `stop()` on shutdown. Two things happen in `start()`: register for discovery (keep the returned **cancel closure** for `stop`), and — crucially — **reconnect to already-paired devices**. On every Hub restart, `start()` is your only chance to do that; skip it and paired devices look "stuck" until re-paired. `controller_did_connect_device` isn't just for "just finished pairing" — call it any time a device becomes reachable, including here at boot, to flip `device.available` back to `True`:

```python
async def start(self):
    self._discoveries = {}
    self._client = AcmeClient()  # pseudo
    self._cancel_discovery = self.dependencies.zeroconf_discovery_service.register(self, {"_acme._tcp.local."})

    async with self.dependencies.make_device_repository() as repo:
        for device in await repo.get_all(self.name, AcmeDevice):
            self._subscribe(device)
            await self.dependencies.output.controller_did_connect_device(self, device.id)

async def stop(self):
    self._cancel_discovery()
    await self._client.close()  # pseudo
```

### Discovery callbacks: identify by hostname, never by IP

The Zeroconf service calls three listener methods (`zeroconf_did_discover_service`, `..._update_service`, `..._remove_service`) because you passed `self` to `register()`. Derive the **stable** discovery id from `info.name` (the mDNS instance name), which stays constant across discover/update/remove for the same physical device — **not** from its IP address:

> If you keyed the id off the IP, a routine DHCP lease renewal would change the address and the Hub would think a *brand-new* device appeared instead of recognizing the one it already knew. Storing a **hostname** in `integration_data` (rather than an IP) sidesteps this entirely: the OS resolves the hostname to the current IP for you, so a paired device changing IP requires no work at all. If you must store an IP, you'd have to update it *and* re-verify reachability on every update event.

`_update_service` only reports a device still in your `discoveries` dict (an unpaired device whose advertisement changed); `_remove_service` gives you only `name`, so pop by the same derived id and call `controller_did_lose_discovery`.

### `pair_device`: validate credentials, then transition the id

**Always validate** that the credentials actually sent match the discovery's advertised options — never trust your own discovery-time guess:

```python
async def pair_device(self, discovery: Discovery, credentials: ProvidedCredentials | None):
    if not credentials or credentials.type not in discovery.expected_credentials_options:
        raise ValueError("Unsupported or missing credentials for this discovery")
    acme_device = await self._client.pair(discovery.id, code=credentials.value)  # pseudo
    device_id = self.device_uuid(acme_device.serial)  # permanent, hardware-level id
    ...
```

The device now has a permanent id, distinct from its (temporary) discovery id. Fetch the placeholder row the Hub created under `discovery.id`, set the real `device.id` and `integration_data`, map its parameters, then `await repo.save(device, discovery.id)` — passing the old id **renames** the row from the discovery id to the new device id in one call. Finally drop it from `discoveries`, `_subscribe`, and report `controller_did_connect_device`.

### `unpair` / `identify` / `fetch`

Thin wrappers over your client: `unpair` tells the device/your bookkeeping to forget the pairing (the Hub removes its own DB row); `identify` makes the device blink/beep so the user can find it; `fetch` pulls a fresh snapshot of every parameter and reports them together as a batch of `DeviceParameterChange` events via `controller_did_receive_events`.

### `send_command`: Hub → device

Called when the user changes something in the app. `command.value` is the new value; `parameter` tells you which property — look up the protocol's own name from your `integration_data`:

```python
async def send_command(self, command: DeviceCommand, device: AcmeDevice, parameter: AcmeParameter):
    await self._client.set_property(
        device.integration_data.device_hostname,
        parameter.integration_data.acme_property_name,
        command.value,
    )  # pseudo
```

### `_subscribe`: device → Hub

Called once per device — after pairing and once per already-paired device at boot. Whenever the device's own state changes, report it. Because protocol callbacks are usually plain (non-async), you schedule the async report as a task:

```python
from majordom_integration_sdk.schemas.event import DeviceParameterChange

def _subscribe(self, device: AcmeDevice):
    def on_property_changed(acme_property_name: str, value):
        event = DeviceParameterChange(
            device_id=device.id,
            parameter_id=self.parameter_uuid(device.id, acme_property_name),
            value=value,
        )
        asyncio.create_task(self.dependencies.output.controller_did_receive_events(self, [event]))

    def on_availability_changed(is_available: bool):
        # Optional mid-session availability: report only if your protocol can detect a *paired*
        # device dropping/returning while the Hub runs. If it can't, omit this entirely.
        cb = (self.dependencies.output.controller_did_connect_device if is_available
              else self.dependencies.output.controller_did_lose_device)
        asyncio.create_task(cb(self, device.id))

    self._client.subscribe(device.integration_data.device_hostname,
                           on_property_changed=on_property_changed,
                           on_availability_changed=on_availability_changed)  # pseudo
```

## What's Deliberately Left Out

The example skips a few things your real integration will likely need, so it doesn't obscure the shape of the interface itself:

- **Error handling** — set `discovery.last_error` / `device.last_error` on failures (see [Implementing a Controller: `last_error`](https://docs.majordom.io/device-integration/controller/#last_error)).
- **`start_pairing_window`** — only implement it if your protocol needs an explicit, short-lived scan mode (Zigbee permit-join, BLE burst scan). Always-on discovery (mDNS, SSDP) doesn't need it.
- **Retry/backoff, connection pooling, rate limiting** — whatever your protocol's client needs; the SDK prescribes nothing here.
- **Implementing the protocol yourself** — the example assumes `AcmeClient` already exists as a high-level SDK (`pair`, `get_properties`, `set_property`, ...). Real protocols don't always have one; if yours doesn't, you may implement the transport, connection management, and serialization directly inside your integration. That's expected. The framework (`AbstractController`, the discovery services, the `Device`/`Parameter` models) is deliberately independent of any protocol's implementation details — and, discovery services and data models in particular being plain public SDK, can be reused standalone (e.g. to build a protocol library outside MajorDom entirely).

## Testing

Test your controller against simulated devices with the SDK's `majordom_integration_sdk.testing` doubles — `build_test_dependencies()` plus `RecordingControllerOutput` — rather than real hardware. See [Testing](https://docs.majordom.io/device-integration/#testing) and the template's own `tests/` for the pattern.
