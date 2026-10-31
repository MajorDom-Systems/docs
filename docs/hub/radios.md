# The SDK Runtime

The runtime is part of the SDK: [`majordom_integration_sdk.runtime`](https://github.com/MajorDom-Systems/integration-sdk/tree/develop/majordom_integration_sdk/runtime), the `runtime` extra. (It used to be the separate `majordom-transports` package, now archived.) The Hub runs it in its own process, and so does the [standalone runner](../device-integration/standalone.md). It runs [peripherals](../device-integration/radios.md#peripherals): it finds the radios, runs the Bluetooth router, Zeroconf and SSDP in-process, binds every need to a provided endpoint, runs the services in Docker, and keeps all of it in sync as sticks come and go. For the integration side (needs, endpoints, services), see [Peripherals and Services](../device-integration/radios.md).

## Package

```
majordom_integration_sdk/
├── peripherals/         # the language: Peripheral, Need, Endpoint, Service, ComposeService, UsbDriver, BLEProxy
├── capabilities/        # contracts of the in-process peripherals: BLERouter, BLESource, BLEConnection, BLELease,
│                        #   BLEMatcher, SecureChannel (ble, ble_security), Zeroconf (zeroconf), SSDP (ssdp)
├── platform.py          # Platform: the host's facts, documents folders, device repository
├── files.py             # read_json / write_json: atomic, owner-only (0600)
├── controller/          # AbstractController; ControllerOutput, IntegrationError (output.py)
├── schemas/             # data models; credentials.py: CredentialsType, CredentialsOption, ProvidedCredentials, WifiCredentials
├── repository/          # device repositories: in-memory, SQLite
├── testing/             # build_test_platform, RecordingControllerOutput, FakeBLESource, FakeBLERouter, FakeZeroconf, FakeSSDP, FakeCompose, FakePeripheral
├── dev/                 # the standalone runner (run_controller, build_platform, build_runtime, Runner) and CLI (run_cli)
└── runtime/             # Runtime (runtime.py), default_peripherals (defaults.py)
    └── peripherals/
        ├── hardware/    # UsbScanner, Radio (usb.py), drivers (drivers.py), soldered radios (fixed.py), host (host.py)
        ├── services/    # the services the runtime brings (builtin.py: silabs-multiprotocol, otbr) and their images/
        └── providers/   # in-process: ble/ (router.py, bluez.py, cpc_hci.py), zeroconf.py, ssdp.py
```

| Extra | Installs | For |
|---|---|---|
| (none) | pydantic, python-slugify | models, controller, peripherals, capabilities: what every integration imports |
| `cli` | typer-shell, rich | the interactive standalone CLI |
| `runtime` | pyserial | the runtime: radios, firmware, services |
| `ble` | bleak, dbus-fast (Linux) | the Bluetooth router's adapters, pairing through BlueZ |
| `discovery` | zeroconf | Zeroconf (DNS-SD over mDNS) |

The Hub and the standalone runner install `majordom-integration-sdk[runtime,ble,discovery]`. An integration depends on the bare SDK, plus the extras its tests use (`ble` for `FakeBLESource`, `discovery` for `FakeZeroconf`).

## From a stick to a running integration

The Hub runs one `Runtime` over, in this order: pinned endpoints, the board's soldered radios, `default_peripherals()` (`UsbScanner`, `BluetoothAdapters`, `HostNetwork`, `Compose`, `silabs-multiprotocol`, `otbr`, the Bluetooth router, Zeroconf, SSDP), then each integration's `peripherals(platform)`.

1. **Find.** The `UsbScanner` lists `/dev/serial/by-id/` every 2 seconds. A change counts once it held for one more look, so a stick that re-enumerates doesn't trigger twice.
2. **Identify.** A stick seen for the first time is identified once: the SDK's drivers (the Z-Wave Serial API, Silicon Labs firmware through `universal-silabs-flasher`), then the `UsbDriver`s integrations export (Zigbee's `ZigpyDriver`). The result is kept. Each stick becomes a `Radio` the scanner brings along (`usb/<stick>`), providing what its firmware serves. A multi-PAN radio is also checked once for [Bluetooth over CPC](radio-images.md#bluetooth-over-cpc).
3. **Bind.** Needs are bound in that order, each to the first provider that can serve it. An exclusive endpoint goes to one consumer; an `is_many` need takes every free one, so the router gets every adapter. A service runs only while something that runs binds it, and only when its own required needs can be bound, so chains form by themselves: Matter → `matterjs-server` → `otbr` → a Thread stick. A need left unbound keeps its reason.
4. **Compose.** `Compose` writes the running services to `compose.json` (project `majordom`) and runs them with `docker compose`. Host-network services listen on `{host.listen_address}`: `127.0.0.1`, or every interface with the Hub's `EXPOSE_SERVICES_ON_LAN` (a lab harness; nothing guards them on the LAN).
5. **Run.** The runtime starts each peripheral once its required needs are bound to providers that run:
    - it stops one when a required need is lost; the Hub tells the user it resumes when the radio is back (error `hub-needs-unbound`);
    - it hands moved needs, settings and platform facts to its hooks, and restarts it unless they handled them;
    - it retries a failed start after 5, 30 and 120 seconds, then marks it failed (error `hub-start-failed`); a peripheral that ran `STABLE_RUN` (300 s) clears its failures;
    - it restarts a running integration that reports `is_still_running=False`.

The Hub keeps each integration's active errors in memory, sends the app `majordom_did_encounter_error` when one is new or changed and `majordom_did_resolve_error` when it is resolved, and drops them all when the integration stops or restarts.

### The Thread network

A border router service (`silabs-multiprotocol` or `otbr`) joins `platform.thread_dataset`, or, with none, forms a network once its REST API answered 15 seconds without one. It then tells the runtime the active dataset (`peripheral_did_learn`). The Hub stores it and hands the new platform to every peripheral (`platform_facts_did_change`), so Matter commissions onto it.

## Where state lives

In the `runtime/` folder of the hub's data folder (`majordom_data/`, or `$MAJORDOM_DATA`). Every file is written whole or not at all, readable by its owner only (`majordom_integration_sdk.files`):

| Path | Holds |
|---|---|
| `state.json` | settings by peripheral key, and what each peripheral keeps |
| `<key>/` | each peripheral's documents folder: `usb/sticks.json` (known sticks), `compose/compose.json` and `compose/ports.json`, each service's data (its `{data}`: Thread and Zigbee network state, the Matter fabric, the Z-Wave cache) |

Back up the data folder: `state.json` holds the generated Z-Wave network keys.

## Firmware

A Silicon Labs stick can run Zigbee (EZSP, firmware `zigbee-ncp`), Thread (Spinel, `thread-rcp`) or multi-PAN (CPC, `multipan-rcp`) firmware; a Z-Wave stick runs `serial-api`. For each radio, `GET /hardware/radios` lists `options`: the firmware it can switch to, and which of the families integrations ask for each one would serve. Switching takes about a minute:

1. The radio is marked `is_busy`. Whatever used it is stopped or unbound.
2. The build is downloaded into `firmware/` and checked against its SHA-256.
3. `universal-silabs-flasher` writes it, and the stick is identified again.

The hub setting `firmware` picks the channel: `stable` (the default) offers verified builds only, `dev` every known build. Builds are listed per board model, matched by the product name in the stick's `/dev/serial/by-id` path.

## Board profiles

Soldered radios have no `/dev/serial/by-id` entry. A MajorDom board lists them in `/etc/majordom/board.json`, written into the OS image:

```json
[{"id": "mg26", "path": "/dev/ttyAMA3", "driver": "silabs", "firmware": "multipan-rcp"}]
```

The Hub uses them as listed, without identifying them, whenever the path exists. Add `"params": {"baud": 115200, "flow_control": false}` where the board wires the UART differently from the firmware's default.

## Radios another program holds

A stick another program has open (zigbee2mqtt, Home Assistant) is not opened or bound. `GET /hardware/radios` shows it as `held_by` that program. Probing it (`POST /hardware/radios/{key}/probe`) claims it anyway.

## Pinned endpoints

To provide an endpoint yourself (a `socket://` EZSP stick on the network, a matter-server you run), give the runtime a `Pinned(endpoint)` first: it wins over anything found, and no container starts for a need it serves.

## In-process providers

Besides radios and services, the runtime runs peripherals in its own process, each providing one shared endpoint with its `instance`. Integrations need them by the SDK's typed needs:

| Key | Provides | Typed need | Needs | Extra |
|---|---|---|---|---|
| `ble-router` (`BLEService`) | `ble/router` | `BLE_ROUTER` | `ble/bluez`, `ble/silabs-cpc-hci`, `ble/esphome-proxy`, `is_many`, optional | `ble` for the host adapters |
| `zeroconf` (`ZeroconfDiscoveryService`) | `mdns/zeroconf` | `ZEROCONF` | — | `discovery` |
| `ssdp` (`SSDPDiscoveryService`) | `upnp/ssdp` | `UPNP_SSDP` | — | — |

They are on demand: each runs while something that runs needs it. The router hears about every adapter that comes up and every `BLEProxy` an integration brings along (`needed_peripheral_did_change`).

## Disabling peripherals

Every peripheral is disabled by its key: `DISABLE_SERVICES=zigbee,ble-router` in the Hub's `.env`, or `POST /integrations/{key}/disable` for an integration (kept across restarts). Old controller class names still work for one release, with a warning. `ENABLE_SERVICES` gates the Hub's own services only.

## REST API

All paths are under `/v1/api`; schemas are in the [API Reference](api.md). A radio's key is `usb/<its /dev/serial/by-id name>`, or its board profile key.

| Method | Path | Does |
|---|---|---|
| `GET` | `/hardware/radios` | radios: `key`, `path`, `driver`, `firmware`, what they serve (`offers`), what each firmware would serve (`options`), `used_by`, `is_busy`, `held_by` |
| `POST` | `/hardware/radios/{key}/firmware?firmware=<firmware>` | switch firmware in the background; answers `202` |
| `POST` | `/hardware/radios/{key}/probe` | identify a stick that isn't a known radio |
| `POST` | `/hardware/radios/{key}/forget` | forget what a radio is; it is identified again while plugged in |
| `GET` | `/integrations` | per integration: `key`, `name`, `status`, `kind` (why it waits or failed), the active `errors`, its `needs`, and its settings keys |
| `POST` | `/integrations/{key}/enable`, `/disable`, `/restart` | the user's switches; disabled stays across restarts |
| `GET` | `/settings/{scope}` | values and JSON schema of a peripheral's settings by its key (integration, service, radio), or the hub's (`hub`); write-only fields left out |
| `PATCH` | `/settings/{scope}` | change some values; what uses them applies them in place or restarts |

Each need in `GET /integrations`:

| Field | Holds |
|---|---|
| `family`, `is_required` | the need |
| `is_many` | `true` when it binds every free matching endpoint; `endpoint` is then a list |
| `provider` | the key of what serves it: a radio, a service, a provider, an integration, `host` or `pinned`; a list for an `is_many` need; `null` while unbound |
| `endpoint` | what it is bound to: `family`, `dialect`, `url`, `is_shared`, `params` (never the in-process instance) |

An integration waiting for a required need has `kind: needs-unbound` and the error `hub-needs-unbound`, which names the missing families ("{name} waits for {families}. It starts once that is there."). Why each is unbound is the runtime's reason, in the Hub's log.

The API Reference is generated from the Hub's OpenAPI schema, which the OpenAPI sync bot regenerates; don't edit it by hand.

## Bluetooth

The runtime's router (`ble/router`) takes every raw Bluetooth endpoint: each host adapter, offered one by one as `ble/bluez` with its `index`; a multi-PAN radio's Bluetooth (`ble/silabs-cpc-hci`, see [Bluetooth over CPC](radio-images.md#bluetooth-over-cpc)); and every connected ESPHome node with `bluetooth_proxy`, a `BLEProxy` the ESPHome integration brings along as `esphome/<bt-mac>` (its *Bluetooth proxies* setting turns that off). Integrations need the router and reach devices through whichever radio hears them best (see [Bluetooth](../device-integration/discovery/ble.md)). An integration that needs raw Bluetooth stays unbound, with the hint to need the router.

By default matterjs-server never touches an adapter. It runs with `BLE_PROXY=true`, and the Matter integration's Bluetooth delegate (`MatterServerBLEDelegate`) connects to its `/ble` endpoint over matterjs-server's [BLE proxy protocol](https://github.com/matter-js/matterjs-server/blob/main/docs/ble-proxy-protocol.md): when matterjs-server commissions a device, it scans, connects and exchanges GATT data through the hub's router, so commissioning works through ESPHome proxies too. With the router disabled, matterjs-server uses a free adapter directly; see [Matter](../integrations/matter.md#bluetooth).

An ESPHome node's Bluetooth proxy serves one hub at a time. Turn the ESPHome integration's *Bluetooth proxies* setting off only if another hub needs it.

## Setup

`system/setup.sh` installs Docker and BlueZ, adds the `majordom` user to the `docker`, `dialout` and `bluetooth` groups, and installs `universal-silabs-flasher`. It also turns on IPv6 forwarding with `accept_ra=2`, so the hub keeps learning the routes other border routers announce.

`--virtual` disables the runtime's hardware and providers by key (`usb`, `board`, `bluetooth-adapters`, `compose`, `ble-router`, `ssdp`, `zeroconf`) and the integrations: no scanning and no Docker.

## Troubleshooting

- **See what runs:** `docker compose -p majordom ps`, then `docker compose -p majordom logs <service>` (`silabs-multiprotocol`, `otbr`, `matterjs-server`, `zwave-js-server`).
- **A stick is recognised as the wrong thing, or not at all**, e.g. after it was flashed on another computer, or while `universal-silabs-flasher` was missing: forget it (`POST /hardware/radios/{key}/forget`) and it is identified again.
- **A USB stick disappears right after you plug it in:** it is usually not fully seated. `dmesg` shows `error -32` or `error -71` from the kernel's USB driver. Push it in all the way.
- **Bluetooth hears nothing:** `busctl get-property org.bluez /org/bluez/hci0 org.bluez.Adapter1 Discovering` should say `b true` while the hub runs. After `bluetoothd` restarts it says `b false` for up to a minute, until the router restarts the silent source. `GET /integrations` shows a need left unbound, with `kind: needs-unbound` and the `hub-needs-unbound` error naming it. matter-server's log shows `BLE proxy handshake complete` once the Matter integration is connected to it.
- **The hub's name changes**, e.g. to `majordom-hub-2.local`: a router on the LAN answers mDNS from its cache, so avahi sees the name as taken and renames the hub. Restart avahi (`sudo systemctl restart avahi-daemon`), then fix the router's mDNS reflector or cache.
