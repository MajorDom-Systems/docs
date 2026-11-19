# Implementing a Controller

Start from the template

Scaffold your integration from the [`integration-template`](https://github.com/MajorDom-Systems/integration-template) (**Use this template → Create a new repository**), and read the [Example Integration](https://docs.majordom.io/device-integration/example-integration/index.md) walkthrough alongside this page — it puts every piece below together in one worked controller.

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

| Situation                     | Action                                                                                                                                                            |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Connection attempt fails      | Set `last_error` to a human-readable message and call the appropriate output method (`controller_did_receive_discovery`, `controller_did_update_discovery`, etc.) |
| Device fetch or command fails | Set `discovery.last_error` / `device.last_error` accordingly                                                                                                      |
| Error is resolved             | Set `last_error = None` explicitly — the Hub never clears it automatically                                                                                        |

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
- **`still_running`** — `False` when the controller can no longer run. The Hub marks the integration **inactive** and tells the user it failed (and what to do, if actionable) — no technical dump. Use `True` for a problem you've handled and recovered from but still want the user to know about (e.g. a user-fixable misconfiguration).

#### Which one do I use?

There are three places an error can go. Pick by asking who it's for and how long it should stay:

| Surface                                      | Use it for                                                                         | How long it lives          |
| -------------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------- |
| `Device.last_error` / `Discovery.last_error` | a problem with one device                                                          | stays until *you* clear it |
| `controller_did_encounter_error`             | the whole integration has a problem; `still_running=False` = it failed and stopped | one-off notification       |
| logs (`logger.*`)                            | technical detail, for you the developer                                            | log retention              |

**What about a parameter failing?** Parameters don't have an error field, on purpose. If one parameter fails (a rejected command, an unreadable value), tell the user at the *device* level and name the parameter in the message: `device.last_error = "Brightness could not be set — the device rejected the command"`. Status codes and tracebacks go to the logs.

Two habits:

- **User surfaces get plain language** — never a traceback or a protocol code.
- **One incident usually goes to two places**: a detailed log line for you, plus one user-facing surface. Logs-only is fine only when the user can't see or fix anything.

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

### `start_pairing_window(duration_sec)`

Optional. Override only if your protocol requires an explicit short-lived scan mode to surface new devices (e.g. Zigbee permit-join, BLE burst scan). Always-on discovery (mDNS, SSDP) does not need this. Default is a no-op.

## Injected Dependencies

The Hub populates `self.dependencies` (see [`AbstractController.Dependencies`](https://github.com/MajorDom-Systems/integration-sdk/tree/master/majordom_integration_sdk/controller/abstract_controller.py)) before calling `start()`.

| Field                        | Type                                                  | Description                                                                          |
| ---------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `output`                     | `ControllerOutput`                                    | Callback object for pushing events to the Hub                                        |
| `make_device_repository`     | `Callable[[], AsyncContextManager[DeviceRepository]]` | Factory for the device repository                                                    |
| `zeroconf_discovery_service` | `ZeroconfDiscoveryService`                            | Shared mDNS/Zeroconf discovery service                                               |
| `ssdp_discovery_service`     | `SSDPDiscoveryService`                                | Shared SSDP discovery service                                                        |
| `ble_discovery_service`      | `BLEDiscoveryService`                                 | Shared BLE scanner service                                                           |
| `hardware_interfaces`        | `list[str]`                                           | OS-level hardware interface paths assigned to this integration (e.g. `/dev/ttyACM0`) |

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
- [Storing Data](https://docs.majordom.io/device-integration/storing_data/index.md) — `integration_data`, typed schemas, file storage, and the device repository
- [Data Models Reference](https://docs.majordom.io/device-integration/data_models/index.md) — `Discovery`, `Device`, `Parameter`, and related types
- [Example Integration](https://docs.majordom.io/device-integration/example-integration/index.md) — a full pseudo-code controller putting all of the above together, to copy as a starting point
