# Zigbee

[`majordom-zigbee`](https://github.com/MajorDom-Systems/integration-zigbee) drives a Zigbee coordinator directly through zigpy. Devices join during an explicit pairing window, so pairing needs no credentials.

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `zigbee` (any dialect: `ezsp`, `znp`, `deconz`, `xbee`, `zigate`, `cc`) | yes | a Silicon Labs stick with Zigbee firmware, a stick `ZigBeeController.probe()` recognises, or the `multiprotocol` service on a multi-PAN stick |

The Hub hands it over as `dependencies.links["zigbee"]`: a serial path, or `socket://…` when the `multiprotocol` service fronts the radio. The link's dialect picks the zigpy radio library, or `auto` probes for it. `ZigBeeController.probe(path)` lets the Hub recognise sticks it doesn't know, so swapping dongles needs no source change.

- **Services it brings:** none. zigpy speaks to the radio directly.
- **Settings:** channel, PAN ID, extended PAN ID, network key and transmit power (`ZigBeeSettings`). Empty values are picked or generated when the network is formed.
- **Context:** none.
- **OS / permissions:** serial-port access to the radio.

The EZSP and Z-Stack (ZNP) libraries are installed by default. ConBee/RaspBee, XBee and ZiGate are extras: `pip install 'majordom-zigbee[deconz]'`, `[xbee]`, `[zigate]`, or `[all-radios]`.

Standalone, pass the coordinator yourself: `links={"zigbee": Endpoint("zigbee", "ezsp", "/dev/ttyUSB0")}` (see [Standalone Mode](../device-integration/standalone.md#connecting-to-radios-and-services)).

For the code behind this, see [Connecting to Radios and Services](../device-integration/radios.md#zigbee-a-radio-directly).
