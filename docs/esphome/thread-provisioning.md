# Thread Provisioning

`thread_provisioning` gives an ESPHome Thread node its network at runtime, over BLE. ESPHome's [`openthread`](https://esphome.io/components/openthread/) component takes the network only at build time (`network_key` or `tlv`), so every network needs an image of its own. With `thread_provisioning`, a single image ships without a network: a controller (the MajorDom Hub, or any client of the protocol below) writes its Thread dataset to the node, the node joins, and is then found over mDNS and paired like any other ESPHome node.

Supported on ESP32 chips with an 802.15.4 radio and BLE (ESP32-C6, ESP32-C5, ESP32-H2), with the ESP-IDF framework.

## How it works

1. The image is built with a **placeholder network**: `openthread:` with a `network_key` only. The placeholder is never joined or formed; while it is the node's active dataset, the node counts as unprovisioned.
2. Unprovisioned, the node keeps Thread off and advertises the provisioning GATT service.
3. A client writes the network's active operational dataset (TLVs). The node checks it is complete, stores it (OpenThread persists it), enables Thread, and waits to attach as a child or router.
4. Once attached, the node reports it, and the service stops 10 s later. It is not advertised again on later boots.
5. If the node cannot attach within `attach_timeout`, it goes back to the placeholder and waits for another dataset.

A factory reset (for example the [`factory_reset`](https://esphome.io/components/button/factory_reset/) button) erases the dataset with the rest of the NVS: the node is unprovisioned again.

## Configuration

```yaml
external_components:
  - source: github://MajorDom-Systems/esphome-components@v0.1.0
    components: [thread_provisioning]

network:
  enable_ipv6: true

openthread:
  # The placeholder network: 32 hex digits, the first not 0. Not a secret, but give each product its own.
  network_key: 0xa300cb8d731d79235840c890f3926d74

thread_provisioning:
  authorizer: boot_button  # optional

api:
  encryption: {}  # no key: the controller sets one at pairing

binary_sensor:
  - platform: gpio
    id: boot_button
    internal: true
    pin:
      number: GPIO9
      inverted: true
      mode: INPUT_PULLUP
```

- **authorizer** (*Optional*, ID): A binary sensor. When set, a dataset is accepted only within `authorized_duration` after it turns on (a button press). `none` or absent: always accepted while unprovisioned.
- **authorized_duration** (*Optional*, Time): How long a press authorizes. Defaults to `1min`.
- **attach_timeout** (*Optional*, Time): How long the node tries to attach with a dataset before it goes back to waiting. Defaults to `60s`.

The `openthread:` block must have `network_key` and no `tlv` or `force_dataset` (a `tlv` would be a real network; `force_dataset` would replace the provisioned dataset on every boot). The build fails otherwise.

A complete example (Seeed XIAO ESP32-C6, also a Bluetooth proxy once on Thread) is in the repository: [`examples/xiao-esp32c6.yaml`](https://github.com/MajorDom-Systems/esphome-components/blob/master/examples/xiao-esp32c6.yaml).

## Protocol

A GATT service modelled on [Improv via BLE](https://www.improv-wifi.com/ble/): the same frames, a different service, and a dataset in place of Wi-Fi credentials.

| Characteristic | UUID | Properties | Value |
|---|---|---|---|
| Service | `aeb52169-9cc0-4883-8ee7-e3d075fbe600` | | advertised while unprovisioned |
| State | `aeb52169-9cc0-4883-8ee7-e3d075fbe601` | read, notify | one byte, see below |
| Error | `aeb52169-9cc0-4883-8ee7-e3d075fbe602` | read, notify | one byte, see below |
| RPC | `aeb52169-9cc0-4883-8ee7-e3d075fbe603` | write | a command frame, in chunks |
| Result | `aeb52169-9cc0-4883-8ee7-e3d075fbe604` | read, notify | a result frame |

A frame is `command, length, data…, checksum`, the checksum being the low byte of the sum of all the previous bytes. A command longer than the connection's ATT MTU is written in consecutive chunks; the node assembles them until `length` bytes of data and the checksum have arrived.

**Command** `0x01` Set dataset: data is the active operational dataset as raw TLVs (as `ot-ctl dataset active -x` prints them, up to 254 bytes). It must include the active timestamp, network key, extended PAN ID, PAN ID, channel and mesh-local prefix. On success the Result is `01 00 01`.

| State | | Error | |
|---|---|---|---|
| `0x01` | awaiting authorization | `0x00` | none |
| `0x02` | authorized | `0x01` | invalid frame (length or checksum) |
| `0x03` | attaching | `0x02` | unknown command |
| `0x04` | attached | `0x03` | unable to attach within `attach_timeout` |
| | | `0x04` | not authorized |
| | | `0x05` | invalid or incomplete dataset |
| | | `0xFF` | unknown |

## Security

The dataset holds the Thread network key. The node never logs it and wipes its copies once used, but over the air the service is plain BLE: anyone in range while the node is unprovisioned can read what a client writes, or write a dataset of their own. Use an `authorizer` on products where a button press is acceptable, and provision in a trusted place. Encrypting the exchange is planned.

## In MajorDom

The Hub's ESPHome integration discovers unprovisioned nodes by the service UUID and offers them as new devices. Pairing one gives it the Hub's Thread network, waits for it on mDNS (through the Hub's border router), sets its API key over the zero PSK, and adds it.
