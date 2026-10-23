# The SDK Runtime

The runtime is part of the SDK: [`majordom_integration_sdk.runtime`](https://github.com/MajorDom-Systems/integration-sdk/tree/master/majordom_integration_sdk/runtime), the `runtime` extra. (It used to be the separate `majordom-transports` package, now archived.) The Hub runs it in its own process, and so does the [standalone runner](../device-integration/standalone.md). It finds the radios, runs the Bluetooth router, DNS-SD and SSDP in-process, decides what serves each integration's needs, runs the services in Docker, and keeps all of it in sync as sticks come and go and integrations offer endpoints. For the integration side (needs, endpoints, services), see [Connecting to Radios and Services](../device-integration/radios.md).

## Package

```
majordom_integration_sdk/
├── peripherals/         # the language: Need, Endpoint, Service, Peripherals, PeripheralChange
├── capabilities/        # contracts of the in-process peripherals: BLERouter, BLESource, BLEConnection, BLELease,
│                        #   BLEMatcher, SecureChannel (ble, ble_security), DNSSD (dns_sd), SSDP (ssdp)
├── controller/          # AbstractController; Platform, Context, ServiceControl, Offers (platform.py); ControllerOutput (output.py)
├── schemas/             # data models; credentials.py: CredentialsType, CredentialsOption, ProvidedCredentials, WifiCredentials
├── repository/          # device repositories: in-memory, SQLite
├── testing/             # build_test_platform, RecordingControllerOutput, FakeBLESource, FakeBLERouter, FakeDNSSD, FakeSSDP, FakeOffers
├── dev/                 # the standalone runner (run_controller, build_platform, build_runtime, Runner) and CLI (run_cli)
└── runtime/             # Runtime, Radio, PlatformSettings (runtime.py)
    └── peripherals/
        ├── hardware/    # radio drivers and their firmware (drivers.py)
        ├── services/    # the services the runtime brings (builtin.py: silabs-multiprotocol, otbr) and their images/
        └── providers/   # in-process: ble/ (router.py, bluez.py, cpc_hci.py), dns_sd.py, ssdp.py
```

| Extra | Installs | For |
|---|---|---|
| (none) | pydantic, python-slugify | models, controller, peripherals, capabilities: what every integration imports |
| `cli` | typer-shell, rich | the interactive standalone CLI |
| `runtime` | pyserial | the runtime: radios, firmware, services |
| `ble` | bleak, dbus-fast (Linux) | the Bluetooth router's adapters, pairing through BlueZ |
| `discovery` | zeroconf | DNS-SD over mDNS |

The Hub and the standalone runner install `majordom-integration-sdk[runtime,ble,discovery]`. An integration depends on the bare SDK, plus the extras its tests use (`ble` for `FakeBLESource`, `discovery` for `FakeDNSSD`).

## From a stick to a running integration

1. **Find.** Every 2 seconds the Hub lists `/dev/serial/by-id/` (USB sticks) and the radios of the [board profile](#board-profiles). A change counts once it held for one more look, so a stick that re-enumerates doesn't trigger twice.
2. **Identify.** A stick seen for the first time is identified once, in this order: the Z-Wave Serial API (one short frame), Silicon Labs firmware through `universal-silabs-flasher probe` (EZSP: Zigbee, Spinel: Thread, CPC: multi-PAN), then each integration's `probe()`. The result is saved. A stick nobody recognises offers nothing. A multi-PAN radio is also checked once for [Bluetooth over CPC](radio-images.md#bluetooth-over-cpc).
3. **Bind.** The [in-process providers](#in-process-providers) are bound first, then each integration in order. Every need is matched to what's on offer: endpoints [reserved](#reservations) for that consumer, endpoints pinned in library mode, the host (`ip`, each Bluetooth adapter as `ble/bluez`), radios by their firmware, services, the providers (`ble/router`, `mdns/dns-sd`, `upnp/ssdp`) and what integrations [offer](../device-integration/radios.md#offering-endpoints). A service is on offer only when its own required needs can be bound, so chains form by themselves: Matter → `matterjs-server` → `otbr` → a Thread stick. An exclusive endpoint goes to one consumer; a `many` need takes every free one. The provider the user [picked](#pins) for a family is tried first. A need left unbound keeps its reason (`unbound`), with a hint when there is something to do.
4. **Compose.** The services that ended up bound are written to `compose.json` (project `majordom`) and started with `docker compose up -d --remove-orphans`, which also removes services nothing uses any more. With none left, the Hub runs `docker compose down`.
5. **Peripherals.** Each integration gets its bound endpoints by family (`Runtime.peripherals(slug)`), or `None` while a required need can't be met (`Runtime.unbound(slug)` says why), and its `Platform` with its settings, the context, its services and its offers (`Runtime.platform(slug, base)`). Each provider hears about what was bound to it.
6. **Sync.** The Hub brings every integration in line:
    - it starts an integration once its required needs are bound;
    - it stops one when a required need is lost, and tells the user it resumes when the radio is back;
    - it restarts one when its peripherals, settings or context changed, unless its hooks (`peripheral_did_change()`, …) handled them;
    - it retries a failed start after 5, 30 and 120 seconds, then reports the integration failed;
    - it restarts a running integration that reports `still_running=False`.

### The Thread network

When a border router is in use, the Hub waits for its Thread network (the active dataset, read over the border router's REST API) and passes it to every integration as `context.thread_dataset`. The `silabs-multiprotocol` service forms its own network. A plain `otbr`, or a border router pinned in library mode, that still has no network after 15 seconds gets one from the Hub, once: the dataset from the service's `dataset` setting, or else a new network named `MajorDom`.

## Where state lives

In the `radios/` folder of the hub's data folder (`majordom_data/`, or `$MAJORDOM_DATA`):

| Path | Holds |
|---|---|
| `state.json` | known radios (driver and firmware, or what an integration's `probe()` found), pins, reservations, service ports, and settings by scope |
| `compose.json` | the Compose project of the bound services |
| `services/<name>/` | each service's data (its `{data}`): Thread and Zigbee network state, the Matter fabric, the Z-Wave cache |
| `firmware/` | downloaded firmware builds |

Back up `state.json` with the rest of the data folder: it holds the generated Z-Wave network keys.

## Firmware

A Silicon Labs stick can run Zigbee (EZSP, firmware `zigbee-ncp`), Thread (Spinel, `thread-rcp`) or multi-PAN (CPC, `multipan-rcp`) firmware; a Z-Wave stick runs `serial-api`. For each radio, `GET /hardware/radios` lists `options`: the firmware it can switch to, and which of the families integrations ask for each one would serve. Switching takes about a minute:

1. The radio is marked `busy`. Whatever used it is stopped or unbound.
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

A stick another program has open (zigbee2mqtt, Home Assistant) is not opened or bound. `GET /hardware/radios` shows it as `held_by` that program. Probing it, or pinning a family to it, claims it anyway.

## Pins

When two radios can serve the same family, e.g. two Thread sticks, the user can prefer one: `PUT /hardware/providers/{family}` with `{"provider": "<radio id or service name>"}`. `{"provider": null}` goes back to automatic. In library mode: `await runtime.pin(family, provider)`; to provide an endpoint yourself, `await runtime.pin_endpoint(endpoint)`.

## Reservations

A reservation keeps one endpoint for one consumer (an integration slug or a service name), bound to it before anyone else, the providers' `many` needs included. It is how one Bluetooth adapter goes to `matterjs-server` instead of the router (Matter's [direct mode](../integrations/matter.md#bluetooth)): `PUT /hardware/reservations/matterjs-server/ble` with `{"url": "hci1"}`. `{"url": null}` gives it back. In library mode: `await runtime.reserve(owner, family, url)`.

## In-process providers

Besides radios and services, the runtime runs peripherals in its own process, each offered as one shared endpoint with its `instance`:

| Provider | Offers | Needs | Extra |
|---|---|---|---|
| `ble-router` (`BLEService`) | `ble/router` | `ble/bluez`, `ble/silabs-cpc-hci`, `ble/esphome-proxy`, `many`, optional | `ble` for the host adapters |
| `ZeroconfDiscoveryService` | `mdns/dns-sd` | — | `discovery` |
| `SSDPDiscoveryService` | `upnp/ssdp` | — | — |

`Runtime(builtins=...)` takes the providers to run; by default one of each whose extra is installed. A provider's needs are bound before any integration's, and it hears about each change of them (`peripheral_did_change`), so the router hears through every adapter that comes up and every proxy an integration offers.

## REST API

All paths are under `/v1/api`; schemas are in the [API Reference](api.md). A radio's id is its `/dev/serial/by-id` name, or its id in the board profile.

| Method | Path | Does |
|---|---|---|
| `GET` | `/hardware/radios` | radios: `id`, `path`, `present`, `driver`, `firmware`, what they serve (`offers`), what each firmware would serve (`options`), `used_by`, `busy` |
| `POST` | `/hardware/radios/{id}/firmware?firmware=<firmware>` | switch firmware in the background; answers `202` |
| `POST` | `/hardware/radios/{id}/forget` | forget what a radio is; it is identified again while plugged in |
| `PUT` | `/hardware/providers/{family}` | prefer a radio or service for a family |
| `PUT` | `/hardware/reservations/{owner}/{family}` | keep one endpoint (`{"url": "hci1"}`) for one integration or service, ahead of the router; `null` gives it back |
| `GET` | `/integrations` | per integration: `status` (`running`, `starting`, `waiting` for a radio, `failed`), `error`, its needs, and its settings scopes |
| `GET` | `/settings/{scope}` | values and JSON schema of an integration's (slug), a service's (name) or the hub's (`hub`) settings |
| `PATCH` | `/settings/{scope}` | change some values; whatever uses them restarts |

Each need in `GET /integrations`:

| Field | Holds |
|---|---|
| `family`, `required` | the need |
| `many` | `true` when it binds every free matching endpoint; `endpoint` is then a list |
| `provider` | who serves it: a radio id, a service or provider name, an integration that offered it, `host` or `pinned`; comma-separated for a `many` need; `null` while unbound |
| `endpoint` | what it is bound to: `family`, `dialect`, `url`, `shared`, `params` (never the in-process instance) |
| `unbound` | why it isn't bound, with what to do when there is something, e.g. `need ble/bluez: every provider taken by ble-router — use Need("ble", ["router"])` |

The API Reference is generated from the Hub's OpenAPI schema, which the OpenAPI sync bot regenerates; don't edit it by hand.

## Bluetooth

The runtime's router (`ble/router`) takes every raw Bluetooth endpoint: each host adapter, offered one by one as `ble/bluez` with its `index`; a multi-PAN radio's Bluetooth (`ble/silabs-cpc-hci`, see [Bluetooth over CPC](radio-images.md#bluetooth-over-cpc)); and every connected ESPHome node with `bluetooth_proxy`, which the ESPHome integration offers as `ble/esphome-proxy` (its *Bluetooth proxies* setting turns that off). Integrations need the router and reach devices through whichever radio hears them best (see [Bluetooth](../device-integration/discovery/ble.md)). An integration that needs raw Bluetooth stays unbound, with the hint to need the router.

By default matterjs-server never touches an adapter. It runs with `BLE_PROXY=true`, and the Matter integration's Bluetooth delegate (`MatterServerBLEDelegate`) connects to its `/ble` endpoint over matterjs-server's [BLE proxy protocol](https://github.com/matter-js/matterjs-server/blob/main/docs/ble-proxy-protocol.md): when matterjs-server commissions a device, it scans, connects and exchanges GATT data through the hub's router, so commissioning works through ESPHome proxies too. With an adapter [reserved](#reservations) for it, matterjs-server uses that one directly; see [Matter](../integrations/matter.md#bluetooth).

An ESPHome node's Bluetooth proxy serves one hub at a time. Turn the ESPHome integration's *Bluetooth proxies* setting off only if another hub needs it.

## Setup

`system/setup.sh` installs Docker and BlueZ, adds the `majordom` user to the `docker`, `dialout` and `bluetooth` groups, and installs `universal-silabs-flasher`. It also turns on IPv6 forwarding with `accept_ra=2`, so the hub keeps learning the routes other border routers announce.

`RADIOS=false` (in `.env`) turns off scanning and Docker: only pinned endpoints, the host's capabilities and the in-process providers are bound. `--virtual` sets it, and also turns off the router, DNS-SD and SSDP (`BLEService`, `ZeroconfDiscoveryService`, `SSDPDiscoveryService`).

## Troubleshooting

- **See what runs:** `docker compose -p majordom ps`, then `docker compose -p majordom logs <service>` (`silabs-multiprotocol`, `otbr`, `matterjs-server`, `zwave-js-server`).
- **A stick is recognised as the wrong thing, or not at all**, e.g. after it was flashed on another computer, or while `universal-silabs-flasher` was missing: forget it (`POST /hardware/radios/{id}/forget`) and it is identified again.
- **A USB stick disappears right after you plug it in:** it is usually not fully seated. `dmesg` shows `error -32` or `error -71` from the kernel's USB driver. Push it in all the way.
- **Bluetooth hears nothing:** `busctl get-property org.bluez /org/bluez/hci0 org.bluez.Adapter1 Discovering` should say `b true` while the hub runs. After `bluetoothd` restarts it says `b false` for up to a minute, until the router restarts the silent source. `GET /integrations` shows a need left unbound and why. matter-server's log shows `BLE proxy handshake complete` once the Matter integration is connected to it.
- **The hub's name changes**, e.g. to `majordom-hub-2.local`: a router on the LAN answers mDNS from its cache, so avahi sees the name as taken and renames the hub. Restart avahi (`sudo systemctl restart avahi-daemon`), then fix the router's mDNS reflector or cache.
