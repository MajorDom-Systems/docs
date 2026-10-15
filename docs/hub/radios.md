# Radios and Transports

The Hub runs [`majordom-transports`](https://github.com/MajorDom-Systems/majordom-transports) in its own process. It finds the radios, decides what serves each integration, runs the services in Docker, and keeps all of it in sync as sticks come and go. For the integration side (needs, endpoints, services), see [Connecting to Radios and Services](../device-integration/radios.md).

## From a stick to a running integration

1. **Find.** Every 2 seconds the Hub lists `/dev/serial/by-id/` (USB sticks) and the radios of the [board profile](#board-profiles). A change counts once it held for one more look, so a stick that re-enumerates doesn't trigger twice.
2. **Identify.** A stick seen for the first time is identified once, in this order: the Z-Wave Serial API (one short frame), Silicon Labs firmware through `universal-silabs-flasher probe` (EZSP: Zigbee, Spinel: Thread, CPC: multi-PAN), then each integration's `probe()`. The result is saved. A stick nobody recognises offers nothing.
3. **Bind.** Each integration's needs are matched to what's on offer: endpoints pinned in library mode, the host (`ip`, `ble`), radios by their firmware, and services. A service is on offer only when its own required needs can be bound, so chains form by themselves: Matter → `matter-server` → `otbr` → a Thread stick. An exclusive endpoint goes to one consumer. The provider the user [picked](#pins) for a family is tried first.
4. **Compose.** The services that ended up bound are written to `compose.json` (project `majordom`) and started with `docker compose up -d --remove-orphans`, which also removes services nothing uses any more. With none left, the Hub runs `docker compose down`.
5. **Links.** Each integration gets its bound endpoints by family, or nothing while a required need can't be met.
6. **Sync.** The Hub brings every integration in line:
    - it starts an integration once its required needs are bound;
    - it stops one when a required need is lost, and tells the user it resumes when the radio is back;
    - it restarts one when its links, settings or context changed, unless `peripheral_did_change()` handled the moved links;
    - it retries a failed start after 5, 30 and 120 seconds, then reports the integration failed;
    - it restarts a running integration that reports `still_running=False`.

### The Thread network

When a border router is in use, the Hub waits for its Thread network (the active dataset, read over the border router's REST API) and passes it to every integration as `context.thread_dataset`. The `multiprotocol` service forms its own network. A plain `otbr`, or a border router pinned in library mode, that still has no network after 15 seconds gets one from the Hub, once: the dataset from the service's `dataset` setting, or else a new network named `MajorDom`.

## Where state lives

In the `radios/` folder of the hub's data folder (`majordom_data/`, or `$MAJORDOM_DATA`):

| Path | Holds |
|---|---|
| `state.json` | known radios (driver and firmware, or what an integration's `probe()` found), pins, and settings by scope |
| `compose.json` | the Compose project of the bound services |
| `services/<name>/` | each service's data (its `{data}`): Thread and Zigbee network state, the Matter fabric, the Z-Wave cache |
| `firmware/` | downloaded firmware builds |

Back up `state.json` with the rest of the data folder: it holds the generated Z-Wave network keys.

## Firmware

A Silicon Labs stick can run Zigbee (EZSP), Thread (Spinel) or multi-PAN (CPC) firmware. For each radio, `GET /hardware/radios` lists `options`: the firmware it can switch to, and which of the families integrations ask for each one would serve. Switching takes about a minute:

1. The radio is marked `busy`. Whatever used it is stopped or unbound.
2. The build is downloaded into `firmware/` and checked against its SHA-256.
3. `universal-silabs-flasher` writes it, and the stick is identified again.

The hub setting `firmware` picks the channel: `stable` (the default) offers verified builds only, `dev` every known build. Builds are listed per board model, matched by the product name in the stick's `/dev/serial/by-id` path.

## Board profiles

Soldered radios have no `/dev/serial/by-id` entry. A MajorDom board lists them in `/etc/majordom/board.json`, written into the OS image:

```json
[{"id": "mg26", "path": "/dev/ttyAMA3", "driver": "silabs", "firmware": "multipan"}]
```

The Hub uses them as listed, without identifying them, whenever the path exists. Add `"params": {"baud": 115200, "flow_control": false}` where the board wires the UART differently from the firmware's default.

## Radios another program holds

A stick another program has open (zigbee2mqtt, Home Assistant) is not opened or bound. `GET /hardware/radios` shows it as `held_by` that program. Probing it, or pinning a family to it, claims it anyway.

## Pins

When two radios can serve the same family, e.g. two Thread sticks, the user can prefer one: `PUT /hardware/providers/{family}` with `{"provider": "<radio id or service name>"}`. `{"provider": null}` goes back to automatic.

## REST API

All paths are under `/v1/api`; schemas are in the [API Reference](api.md). A radio's id is its `/dev/serial/by-id` name, or its id in the board profile.

| Method | Path | Does |
|---|---|---|
| `GET` | `/hardware/radios` | radios: `id`, `path`, `present`, `driver`, `firmware`, what they serve (`offers`), what each firmware would serve (`options`), `used_by`, `busy` |
| `POST` | `/hardware/radios/{id}/firmware?firmware=<firmware>` | switch firmware in the background; answers `202` |
| `POST` | `/hardware/radios/{id}/forget` | forget what a radio is; it is identified again while plugged in |
| `PUT` | `/hardware/providers/{family}` | prefer a radio or service for a family |
| `GET` | `/integrations` | per integration: `status` (`running`, `starting`, `waiting` for a radio, `failed`), `error`, its needs with their providers, and its settings scopes |
| `GET` | `/settings/{scope}` | values and JSON schema of an integration's (slug), a service's (name) or the hub's (`hub`) settings |
| `PATCH` | `/settings/{scope}` | change some values; whatever uses them restarts |

## Bluetooth

The hub's `BLEService` listens on every local adapter and on every connected ESPHome device with `bluetooth_proxy` (the ESPHome integration adds them; its *Bluetooth proxies* setting turns that off). Integrations reach devices through whichever radio hears them best (see [Bluetooth](../device-integration/discovery/ble.md)).

matter-server never touches the adapter. It runs with `BLE_PROXY=true`, and the Matter integration's Bluetooth delegate (`MatterServerBLEDelegate`) connects to its `/ble` endpoint over matter-server's [BLE proxy protocol](https://github.com/matter-js/matterjs-server/blob/main/docs/ble-proxy-protocol.md): when matter-server commissions a device, it scans, connects and exchanges GATT data through the hub's `BLEService`, so commissioning works through ESPHome proxies too.

An ESPHome node's Bluetooth proxy serves one hub at a time. Turn the ESPHome integration's *Bluetooth proxies* setting off only if another hub needs it.

## Setup

`system/setup.sh` installs Docker and BlueZ, adds the `majordom` user to the `docker`, `dialout` and `bluetooth` groups, and installs `universal-silabs-flasher`. It also turns on IPv6 forwarding with `accept_ra=2`, so the hub keeps learning the routes other border routers announce.

`RADIOS=false` (in `.env`) turns off scanning and Docker: only pinned links and the host's capabilities are bound. `--virtual` sets it.

## Troubleshooting

- **See what runs:** `docker compose -p majordom ps`, then `docker compose -p majordom logs <service>` (`multiprotocol`, `otbr`, `matter-server`, `zwave-js`).
- **A stick is recognised as the wrong thing, or not at all**, e.g. after it was flashed on another computer, or while `universal-silabs-flasher` was missing: forget it (`POST /hardware/radios/{id}/forget`) and it is identified again.
- **A USB stick disappears right after you plug it in:** it is usually not fully seated. `dmesg` shows `error -32` or `error -71` from the kernel's USB driver. Push it in all the way.
- **Bluetooth hears nothing:** `busctl get-property org.bluez /org/bluez/hci0 org.bluez.Adapter1 Discovering` should say `b true` while the hub runs. After `bluetoothd` restarts it says `b false` for up to a minute, until the hub restarts its scanner. matter-server's log shows `BLE proxy handshake complete` once the Matter integration is connected to it.
- **The hub's name changes**, e.g. to `majordom-hub-2.local`: a router on the LAN answers mDNS from its cache, so avahi sees the name as taken and renames the hub. Restart avahi (`sudo systemctl restart avahi-daemon`), then fix the router's mDNS reflector or cache.
