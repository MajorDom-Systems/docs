# Multi-PAN Radio Images

One Silicon Labs multi-PAN RCP can serve Zigbee and Thread at the same time, with no reflashing to switch protocols. The `silabs-multiprotocol` service of the [SDK runtime](radios.md) runs it as one container image (`majordom_integration_sdk/runtime/peripherals/services/images/`). Two images exist, for two SDK generations.

```
USB stick or UART (multi-PAN RCP)
   │
 cpcd  ── iid 1 ── zigbeed ── EZSP pty ── socat ── tcp :9999 ──── Zigbee integration
       └─ iid 2 ── otbr-agent ── Thread ── REST :8081 ─────────── matterjs-server (ws :5580)
```

The Hub talks TCP, WebSocket and REST only. Never run another Zigbee or Thread stack against the same stick: `cpcd` owns it.

| Image | RCP firmware | CPC protocol | For |
|---|---|---|---|
| `multiprotocol` | GSDK 4.4.x, over the Silicon Labs base image | v5 | EFR32MG21 sticks such as SkyConnect |
| `multiprotocol-sisdk` | SiSDK 2025.6.3 | v6 | EFR32MG26, such as the MG26 on the CM4 board |

Host programs and RCP firmware must come from the same SDK release. With a mismatch, network operations hang while `info` still works. Pin the image and the firmware together.

## Behaviour

- **One channel.** A multi-PAN radio listens on one channel; networks on two lose frames, and a Thread device then can't attach. Zigbee forms on `CHANNEL`, and a marker in its state volume records it. At every start the Hub's Thread network moves to that channel if it is elsewhere (as a pending dataset, so attached devices follow). A Thread network joined from outside (`THREAD_DATASET`) is only warned about.
- **The stick's tty is not pinned.** `RADIO_DEVICE` may be a `/dev/serial/by-id` path. It is resolved at every start, and a USB re-enumeration kills `cpcd`, so the container restarts onto the stick's new tty.
- **Transmit power.** The radio sends at Zigbee's power. `ot-ctl txpower` reads back but isn't applied.
- **No energy scans.** Don't run `ot-ctl scan energy` on this stack. It wedges `otbr-agent` until restarted: the host waits without a timeout for a result the multi-PAN RCP never sends, and RCP recovery doesn't reset a multi-PAN RCP (openthread [#13702](https://github.com/openthread/openthread/pull/13702), [#11273](https://github.com/orgs/openthread/discussions/11273), [#11277](https://github.com/openthread/openthread/pull/11277)). If one is needed, scan a single channel briefly under a timeout: `timeout 15 ot-ctl scan energy 10 15`.

### Bluetooth over CPC

A multi-PAN RCP whose firmware also carries the Bluetooth controller serves HCI over CPC next to 802.15.4: `cpcd`'s `cpc-hci-bridge` exposes it as a pty, and `btattach` makes that a BlueZ adapter (`hciN`), which the [Bluetooth router](../device-integration/discovery/ble.md) hears through like any other. The radio then provides its `ble/silabs-cpc-hci` endpoint too, with the adapter in `params["hci"]` once the multiprotocol service attaches it.

It is provided only when the radio's firmware has Bluetooth: from the driver's firmware metadata (`UsbDriver.bluetooth`, the firmware names that serve it) where it knows, else from `cpc_hci.has_bluetooth(path)`, asked once per radio and saved. None of the current builds serves Bluetooth: NabuCasa's multi-PAN RCP is 802.15.4 only, so `bluetooth` stays empty.

`has_bluetooth` is not verified on hardware and answers no for now. To verify on a radio with a Bluetooth-capable multi-PAN build:

1. Which CPC endpoint answers for Bluetooth on that firmware.
2. How to ask `cpcd` without taking the port from the multiprotocol container.
3. The `hciN` the bridge comes up as, to fill `params["hci"]`.

### Why Zigbee forms inside the container

EZSP `form` is a latency-sensitive radio-level sequence, and it can't cross the EZSP-to-TCP bridge: `zigbeed`, pty and `socat` lose ASH frames, so `networkInit` times out. Version negotiation and steady-state commands work fine over the bridge. So `entrypoint.sh` forms the coordinator on the pty, as the single reader, before exposing TCP, when the NCP reports `NOT_JOINED`. The coordinator persists in NCP flash, so later starts skip it, and the Hub only loads it over `socket://…:9999`. `bellows` and `zigpy` are baked into the image, so a first boot forms offline.

## The SiSDK 2025.6.3 image

It replaces `multiprotocol` for radios whose RCP is built on SiSDK 2025.6.3.

| Component | Version | Source | License |
|---|---|---|---|
| cpcd, libcpc | 4.7.1.0 (the deb is labelled 4.6.0) | SiSDK v2025.6.3 `debian-bookworm.zip` | Silicon Labs MSLA |
| zigbeed | 8.2.2 (EmberZNet 8.2.2.0, EZSP v18) | same | MSLA |
| otbr-agent, ot-ctl | ot-br-posix 2.7.3.0 | same | MSLA + BSD-3-Clause (OpenThread) |
| mdnsd, libdns_sd | built from the source in the ot-br-posix deb | same | Apache-2.0 / BSD-3-Clause |
| bellows, zigpy, aiosqlite | 0.49.2, 2.0.1, 0.21.0 | PyPI | GPL-3.0 (bellows, zigpy), MIT |
| Base | `debian:bookworm-slim`, Python 3.11 | Debian | various |

The release zip is pinned by SHA-256 (`SISDK_DEBS_SHA256` in the Dockerfile). Only the target architecture's debs are unpacked, and their maintainer scripts never run (they would pull in bind9, nodejs, radvd and rsyslog). otbr-web is not included. The image is about 210 MB on arm64 and 176 MB on amd64 (62 MB compressed each), against 1.98 GB for the GSDK image.

### Build

```sh
docker buildx build --platform linux/arm64 -t majordom/multiprotocol:sisdk-2025.6.3-arm64 --load .
docker buildx build --platform linux/amd64 -t majordom/multiprotocol:sisdk-2025.6.3-amd64 --load .
```

On a Pi 5, the arm64 build takes about 1.5 minutes and the amd64 build 4 to 8 minutes under QEMU. A multi-arch index needs a `docker-container` buildx builder and `--push`; pin that index digest, not a local image ID. The build fails if any copied binary is missing a shared library.

### Run

```sh
docker run -d --name silabs-multiprotocol --privileged --network host \
  -v /dev/serial:/dev/serial:ro -v otbr-data:/var/lib/thread -v zigbee-data:/var/lib/zigbee \
  -e RADIO_DEVICE=/dev/serial/by-id/<stick> majordom/multiprotocol:sisdk-2025.6.3-arm64
```

`entrypoint.sh` and `cpcd.conf.tmpl` are part of the image, so nothing needs mounting. The entrypoint renders `/etc/cpcd.conf` from the environment; a mounted `/etc/cpcd.conf` is used as is. The other environment variables are listed at the top of `entrypoint.sh`. For a radio on a bare UART:

```
RADIO_DEVICE=/dev/ttyAMA3 RADIO_BAUD=115200 RADIO_HARDFLOW=false RADIO_RESET_GPIO=gpiochip0:23
```

`RADIO_RESET_GPIO` pulses RESETn about 1.5 s after `cpcd` starts and holds the line high while the container runs; once it exits, the line is released. On the CM4, GPIO23 has its pull-down enabled, so give RESETn a pull-up on the PCB.

Compared with the GSDK entrypoint, `cpcd`'s readiness line is now "Connected to Secondary". Also, a Zigbee form counts only when it exits 0: bellows 0.46 doesn't know EZSP v18, and its form crashed while the old success check still matched an aiosqlite traceback and wrote the "formed" marker.

### Validated

On an MG26 running the SiSDK 2025.6.3 multi-PAN RCP:

- `cpcd` reported `Secondary Protocol v6` and `Secondary CPC v4.7.1`.
- `ot-ctl state` returned `leader`, and REST `/node/state` returned `"leader"`.
- `bellows info` over `socket://127.0.0.1:9999` returned `JOINED_NETWORK`, `COORDINATOR` and `EmberZNet version: 8.2.2.0 build 532`.
- After a restart, the stack restored both networks (the same Zigbee PAN) instead of forming new ones.

## Licensing

- **Silicon Labs binaries.** The image carries `cpcd`, `zigbeed` and `otbr-agent` unmodified, as object code under the MSLA (`/usr/share/doc/silabs/MSLA`). The MSLA permits distribution to end users only for use with Silicon Labs devices (§4.2.5).
- **GPL components.** bellows and zigpy are GPL-3.0. They run as separate programs, which is plain aggregation. Their licence texts are in their `dist-info` directories, and the source is unmodified PyPI releases.
- **Notices.** The OpenThread BSD-3 text and the component list are in `/usr/share/doc/majordom-multiprotocol/`.

## Choosing multi-PAN

| Option | Notes |
|---|---|
| RCP host-stack multi-PAN (this) | A dumb multi-PAN RCP on the stick; `cpcd`, `zigbeed` and `otbr` run on the host. Works on EFR32MG21. |
| Home Assistant's Silicon Labs Multiprotocol add-on | The same stack, tied to the HA Supervisor, and deprecated by Nabu Casa in 2025. |
| Dynamic Multiprotocol (DMP) | On-chip time-slicing, used for BLE plus 802.15.4, not for Zigbee plus Thread on a gateway. |
| Two radios | One Zigbee coordinator and one Thread RCP. The most robust, and what Nabu Casa now recommends. |
| Newer silicon | EFR32MG24/MGM240 (more RAM) or Series 3 SiMG301 (native concurrent multiprotocol). |

The MG21 is below Silicon Labs' recommended RAM for multi-PAN, and the host stack is upstream-deprecated. That is fine for development, but risky as the only path in a product.

If you ship multi-PAN on one stick:

1. Pin the image digest and the RCP firmware together.
2. Enable CPC security (build and flash an RCP with it on, provision a binding key) instead of `disable_encryption: true`.
3. Bake the pinned images into the OS image and stage the firmware there, so a field unit needs no network to come up. The stick's own firmware is separate silicon and is flashed at manufacturing.
4. Send `cpcd`, `zigbeed` and `otbr` logs to the journal and alert on the container's health check. A wedged RCP (`cp210x … -110`) is the most common field failure; automate the USB bus reset.
5. Use the arm64 image on the stock Raspberry Pi OS arm64 kernel (16 KB pages). Only a legacy 32-bit image needs the 4 KB `kernel8.img`.
6. Prefer Silicon Labs' own sources: `siliconlabsinc/multiprotocol` (or a build from `cpc-daemon`, the GSDK's `zigbeed` and `ot-br-posix`), firmware built from the GSDK `rcp-uart-802154` sample, and Simplicity Commander as the flasher. `universal-silabs-flasher` is the fallback.
