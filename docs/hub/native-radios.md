# Radios Without Docker (CM4)

On a Compute Module 4 board with soldered radios, the radio stack can run as systemd services instead of containers. The Hub then reads the endpoints it publishes (see `majordom_hub/coordinator.py`). The unit files and `majordom-cpcd.sh` are in `system/cm4-native/` of the Hub repository.

```
majordom-cpcd            CPC daemon on /dev/ttyAMA3; the wrapper pulses RESETn (GPIO23)
  ├─ majordom-otbr           otbr-agent -> Thread   (spinel+cpc://cpcd_0?iid=2)
  ├─ majordom-zigbee-socat   PTY pair /dev/ttyZigbeeNCP <-> /tmp/ttyZigbeeNCP
  │    └─ majordom-zigbeed    zigbeed -> Zigbee     (spinel+cpc://cpcd_0?iid=1) -> EZSP on the PTY
  └─ majordom-matter         matterjs-server on :5580 (uses otbr via IP/mDNS; BLE through the CM4's hci0)
```

Copy `majordom-cpcd.sh` to `/usr/local/bin/` and the `*.service` files to `/etc/systemd/system/`. Then run `systemctl enable --now` in order: cpcd, zigbee-socat, zigbeed, otbr, matter.

## matterjs-server

matterjs-server needs no build. A CM4 running Debian trixie, like the image the Matter integration pins, can take Node and the app straight out of that image. Do it on a host with Docker, then copy the result over:

```sh
C=$(docker create <image>) && docker cp $C:/app app && docker cp $C:/usr/local/bin/node node
```

Put both into `/opt/matterjs-server`. It keeps its data in `/home/admin/matter-data-js`. Data from the archived python-matter-server is not carried over.

## Caveats

- Paths in the units are hardcoded to a development layout (`/home/admin/ot-br-posix/…`, `/home/admin/build-zigbeed/…`, `/opt/matterjs-server`, `/home/admin/matter-data-js`). Parameterise them and install to system locations before shipping.
- Newer `zigbeed` builds support `--ezsp-listen 127.0.0.1 --ezsp-listen-port 9999`. That drops the socat unit; point bellows at `socket://127.0.0.1:9999`, like the container path.
- `cpcd`, the RCP firmware, `zigbeed` and the otbr CPC vendor files must all come from the same SiSDK generation (2025.6.3, CPC 4.7.1).
- This is a reference of the working configuration. It isn't part of `setup.sh` or the OS image build yet.
