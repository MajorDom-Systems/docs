# Zigbee

[`majordom-zigbee`](https://github.com/MajorDom-Systems/integration-zigbee) drives a Zigbee coordinator directly through zigpy. Devices join during an explicit pairing window, so pairing needs no credentials.

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `zigbee` (every zigpy dialect: `ezsp`, `znp`, `deconz`, `xbee`, `zigate`, `ziggurat`, `blz`, `cc`) | yes | a Silicon Labs stick with Zigbee firmware, a stick its `ZigpyDriver` recognises, or the `silabs-multiprotocol` service on a multi-PAN stick |

The Hub hands it over as `self.peripherals.endpoint("zigbee")`: a serial path, or `socket://…` when the `silabs-multiprotocol` service fronts the radio. The endpoint's dialect picks the zigpy radio library, or `auto` probes for it. `ZigpyDriver`, exported next to the controller, lets the runtime's USB scanner recognise sticks it doesn't know, so swapping dongles needs no source change.

- **Services it brings:** none. zigpy speaks to the radio directly.
- **Settings:** transmit power; channel, PAN ID and extended PAN ID are read-only, filled in once the network forms.
- **OS / permissions:** serial-port access to the radio.

The EZSP and Z-Stack (ZNP) libraries are installed by default. ConBee/RaspBee, XBee, ZiGate, Ziggurat and Bouffalo Lab (BLZ) are extras: `pip install 'majordom-zigbee[deconz]'`, `[xbee]`, `[zigate]`, `[ziggurat]`, `[blz]`, or `[all-radios]`.

Standalone, the runtime finds the stick as the Hub does. To pass the coordinator yourself: `run_controller(majordom_zigbee.peripherals, peripherals={"zigbee": Endpoint("zigbee", "ezsp", "/dev/ttyUSB0")})` (see [Standalone Mode](../device-integration/standalone.md#connecting-to-radios-and-services)).

For the code behind this, see [Peripherals and Services](../device-integration/radios.md#zigbee-a-radio-directly).
