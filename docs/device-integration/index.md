# MajorDom Device Integration Guide

!!! warning "Under active development"
    MajorDom is still under development.  
    The integration structure is now stable, but implementation details are still subject to change.

An **integration** is a standalone Python package that bridges MajorDom Hub with IoT devices of a specific protocol or vendor (e.g. HomeKit, Zigbee, Z-Wave). It depends only on the published [`majordom-integration-sdk`](https://pypi.org/project/majordom-integration-sdk/) — not on the Hub source — so it can be developed, tested, and even run on its own.

### Getting started

Don't start from a blank folder. Every integration is scaffolded from the **[`integration-template`](https://github.com/MajorDom-Systems/integration-template)** repository: click **Use this template → Create a new repository**, name it `integration-<protocol>`, and follow the template README's checklist (rename the placeholder package to `majordom_<protocol>`, `poe install`, wire up CI and PyPI publishing). The template ships a working example controller, tests, and CI, so you replace pieces rather than assemble them from scratch. This guide explains the concepts behind that code.

### Licensing

The SDK and the official integrations are released under [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/) — free for noncommercial use. For commercial licensing or partnership, see <https://parker-industries.org/partnership>.

---

### Concepts

| Term | Meaning |
|---|---|
| **Hub** | The MajorDom Hub core software |
| **Integration** | A protocol/vendor-specific plugin |
| **Discovery Service** | A Hub-provided transport-level service (Zeroconf/mDNS, SSDP, or BLE) that fires raw discovery events. Injected via `self.dependencies`. |
| **Controller** (capitalized) | The class your integration must implement (`AbstractController` subclass) |
| **a controller** (lowercase) | Any third-party device that can control IoT devices (smartphone, Alexa, etc.) |
| **Discovery** | A detected, unpaired device that is available to be paired |
| **Device** | A paired and controllable device saved in the Hub's database |
| **Parameter** | A single controllable or observable property of a device (e.g. brightness, temperature) |

A device moves through these states:

```
Invisible → Discoverable (Discovery) → Paired (Device)
```


---

## Suggested Module Structure

Your integration is its own package, `majordom_<protocol>/` (the template starts you with this — `integration_template/` renamed). An integration will typically need more than just a controller. Recommended minimal layout:

```
majordom_myintegration/
├── __init__.py          # exports your controller class
├── controller.py        # AbstractController subclass — the only required implementation; discovery callbacks and cancel closures are typically stored here too
├── models.py            # Typed integration_data schemas for Device and Parameter subclasses, see Storing Data
├── mapper.py            # Protocol ↔ MajorDom domain model conversions, isolated from the controller for readability
└── parameters_map.py    # Supplemental metadata for parameters that the API does not expose, usually in a form of a static dictionary. For example, device might expose min/max limits for a number via device's API, but the unit is only defined in pdf specification.
```

**`controller.py`** is the only required implementation. The rest are a template for keeping the controller clean — separate models, pull out conversion logic into a mapper, add metadata dictionary, etc. Of course, other files can be added as needed.

---

## Implementation Checklist

Track it in your repo: the [integration template](https://github.com/MajorDom-Systems/integration-template#progress)
README ships this and the [Quality Checklist](quality.md) as a fillable copy — tick items there as
you implement them. The list below is the reference.

- [ ] Discovery service listeners fire when devices are found, and the controller calls `self.dependencies.output.controller_did_receive_discovery`
- [ ] Discovery services registered via `self.dependencies.zeroconf_discovery_service`, `ssdp_discovery_service`, and/or `ble_discovery_service` as appropriate; cancel closures saved and called in `stop`
- [ ] Discovery of devices already paired to the Hub on reconnect, e.g. after a reboot (`self.dependencies.output.controller_did_connect_device` is called)
- [ ] `start_pairing_window` is implemented if the protocol requires an explicit scan mode
- [ ] Device pairing (`pair_device` is implemented, and validates the incoming `ProvidedCredentials.type` against `discovery.expected_credentials_options` before using it)
- [ ] Device schema is properly mapped: device info, parameter list, and each parameter's metadata are translated to MajorDom's domain model
- [ ] Hub → Device control (`send_command` is implemented)
- [ ] Device → Hub event subscription (`self.dependencies.output.controller_did_receive_events` is called on incoming events)
- [ ] `identify`, `unpair`, and `fetch` are implemented
- [ ] Paired devices going offline/coming back online *while the Hub is running* (not just on reboot) — set `device.available` accordingly, and clear/set `last_error` to match
- [ ] Graceful shutdown in `stop`
- [ ] **Quality:** once it's functional, the integration meets the [Quality Checklist](quality.md) — reliability, tests, and maintainability — before release

See [Implementing a Controller](controller.md) for details, or [Example Integration](example-integration.md) for a narrative walkthrough of the template's controller. The template README mirrors this checklist as its **Progress** list, so you can track your integration against it directly in your repo.

## Running standalone

You don't need a running Hub to develop an integration. The SDK ships a dev runner that wires your controller to real discovery services and a local repository, starts it, and logs everything it discovers:

```python
import asyncio
from majordom_integration_sdk.dev import run_controller
from majordom_myintegration import MyController

asyncio.run(run_controller(MyController))
```

Pass `db_path=...` to persist devices across restarts (a file-backed SQLite repository) instead of the default in-memory one. See `majordom_integration_sdk.dev` for `build_dependencies`, which returns the same dependency set for your own scripts.

## Testing

Integrations run their tests against a virtual/simulated device where possible, so CI doesn't need physical hardware. The SDK's `majordom_integration_sdk.testing` module provides the doubles: `build_test_dependencies()` wires a `RecordingControllerOutput`, an in-memory repository, and fake discovery services, so a test can drive your controller and assert on what it reported. The template's `tests/` show the pattern. (Real-hardware validation lives in the Hub, not in the integration package.)

## Notes

### For IP Devices

- **Handle IP changes.** DHCP can reassign addresses. Identify devices by a stable ID (MAC, serial, mDNS hostname, domain-provided id) rather than IP. Monitor ip address regularly and keep it up to date.
- **Use the Hub's provided discovery.** Register your mDNS service types via `self.dependencies.zeroconf_discovery_service.register(...)`, and similar for SSDP and BLE. See [Discovery Services](discovery/index.md) for details. Do not spin up your own discovery stack unless absolutely needed.
