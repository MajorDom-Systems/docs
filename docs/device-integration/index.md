# MajorDom Device Integration Guide

!!! warning "Under active development"
    MajorDom is still under development.  
    The integration structure is now stable, but implementation details are still subject to change.

An **integration** is a standalone Python package that bridges MajorDom Hub with IoT devices of a specific protocol or vendor (e.g. HomeKit, Zigbee, Z-Wave). It depends only on the published [`majordom-integration-sdk`](https://pypi.org/project/majordom-integration-sdk/) — not on the Hub source — so it can be developed, tested, and even run on its own.

### Getting started

Don't start from a blank folder. Every integration is scaffolded from the **[`integration-template`](https://github.com/MajorDom-Systems/integration-template)** repository: click **Use this template → Create a new repository**, name it `integration-<protocol>`, and follow the template README's checklist (rename the placeholder package to `majordom_<protocol>`, `poe install`, wire up CI and PyPI publishing). The template ships a working example controller, tests, and CI, so you replace pieces rather than assemble them from scratch. This guide explains the concepts behind that code.

### Licensing

The SDK and the integration template are released under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0): use them freely, for MajorDom integrations or in your own projects, including library mode. We do ask you to keep what you build on them open source.

Most official integrations are source-available for noncommercial use. For a commercial license, contact us — we're open to partnership: <https://parker-industries.org/partnership>.

---

### Concepts

| Term | Meaning |
|---|---|
| **Hub** | The MajorDom Hub core software |
| **Integration** | A protocol/vendor-specific plugin |
| **Need** | Something external the integration requires: a radio, a server, or a discovery peripheral (DNS-SD, SSDP, the Bluetooth router). The Hub binds it and hands it over in `self.peripherals`. See [Connecting to Radios and Services](radios.md) |
| **Discovery Service** | A peripheral the Hub runs in-process (DNS-SD over mDNS, SSDP, or the Bluetooth router) that fires raw discovery events. Needed like any other, see [Discovery Services](discovery/index.md) |
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

- [ ] Discovery registered with the peripherals it needs — `self.peripherals.instance("mdns")` (DNS-SD), `"upnp"` (SSDP) and/or `"ble"` (the Bluetooth router) as appropriate; cancel closures saved and called in `stop`
- [ ] Discovery listeners fire when devices are found, and the controller calls `self.platform.output.controller_did_receive_discovery`
- [ ] Discovery of devices already paired to the Hub on reconnect, e.g. after a reboot (`self.platform.output.controller_did_connect_device` is called)
- [ ] `start_pairing_window` is implemented if the protocol requires an explicit scan mode
- [ ] Device pairing (`pair_device` is implemented, and validates the incoming `ProvidedCredentials.type` against `discovery.expected_credentials_options` before using it)
- [ ] Device schema is properly mapped: device info, parameter list, and each parameter's metadata are translated to MajorDom's domain model
- [ ] Hub → Device control (`send_command` is implemented)
- [ ] Device → Hub event subscription (`self.platform.output.controller_did_receive_events` is called on incoming events)
- [ ] `identify`, `unpair`, and `fetch` are implemented
- [ ] Paired devices going offline/coming back online *while the Hub is running* (not just on reboot) — set `device.available` accordingly, and clear/set `last_error` to match
- [ ] Graceful shutdown in `stop`
- [ ] Everything external declared as a `Need` — radios, `ble/router`, `mdns/zeroconf`, `upnp/ssdp`, the services it brings; never raw Bluetooth
- [ ] Resolved needs read from `self.peripherals`, Hub-provided app services from `self.platform`
- [ ] Integration-level problems reported with a stable error id (`IntegrationError`) and resolved when they clear
- [ ] **Quality:** once it's functional, the integration meets the [Quality Checklist](quality.md) — reliability, tests, and maintainability — before release

See [Implementing a Controller](controller.md) for details, or [Example Integration](example-integration.md) for a narrative walkthrough of the template's controller. The template README mirrors this checklist as its **Progress** list, so you can track your integration against it directly in your repo.

## Running standalone

You don't need a running Hub to develop an integration. The SDK ships a dev runner that binds your controller's needs through the SDK runtime, as the Hub does (the Bluetooth router, DNS-SD, SSDP, radios and services), gives it a local repository, starts it, and logs everything it discovers:

```python
import asyncio
from majordom_integration_sdk.dev import run_controller
from majordom_myintegration import MyController

asyncio.run(run_controller(MyController))
```

It needs the runtime extras: `pip install "majordom-integration-sdk[runtime,ble,discovery]"`. Pass `db_path=...` to persist devices across restarts (a file-backed SQLite repository) instead of the default in-memory one. See [Standalone Mode](standalone.md) for the interactive CLI, `build_platform` for your own scripts, and running without Docker or radios.

## Testing

Integrations run their tests against a virtual/simulated device where possible, so CI doesn't need physical hardware. The SDK's `majordom_integration_sdk.testing` module provides the doubles: `build_test_platform()` wires a `RecordingControllerOutput`, an in-memory repository and temp-dir storage, and `FakeZeroconf`, `FakeSSDP`, `FakeBLERouter` (with `FakeBLESource`s) and `FakeOffers` stand in for the peripherals, so a test can drive your controller and assert on what it reported. The template's `tests/` show the pattern. (Real-hardware validation lives in the Hub, not in the integration package.)

## Notes

### For IP Devices

- **Handle IP changes.** DHCP can reassign addresses. Identify devices by a stable ID (MAC, serial, mDNS hostname, domain-provided id) rather than IP. Monitor ip address regularly and keep it up to date.
- **Use the Hub's provided discovery.** Declare `Need("mdns", ["zeroconf"])` and register your mDNS service types via `self.peripherals.instance("mdns").register(...)`, and similar for SSDP and BLE. See [Discovery Services](discovery/index.md) for details. Do not spin up your own discovery stack unless absolutely needed.
