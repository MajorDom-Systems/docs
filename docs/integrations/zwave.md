# Z-Wave

[`majordom-zwave`](https://github.com/MajorDom-Systems/integration-zwave) talks JSON over a WebSocket to [`zwave-js-server`](https://github.com/zwave-js/zwave-js-server), the server Home Assistant's Z-Wave JS integration also uses. The server holds the serial connection to the Z-Wave controller and speaks the protocol.

## Needs

| Capability | Required | Provided by |
|---|---|---|
| `zwave/zwave-js-ws` | yes | the `zwave-js-server` service below; standalone, any `zwave-js-server` you run |
| `zwave/serial-api` (for `zwave-js-server`) | yes | a Z-Wave USB controller (for example Aeotec or Zooz Z-Stick), recognised by the Hub through the Serial API |

- **Services it brings:** `zwave-js-server`, a container the Hub runs while a Z-Wave stick is plugged in.
- **Settings:** the network's security keys (`ZwaveNetwork`, settings of the `zwave-js-server` service), generated once. Back them up: without them, securely included devices have to be re-included.
- **Context:** the RF region (`context.region`, from the Hub's region setting).
- **OS / permissions:** network reachability (TCP) to `zwave-js-server` when you run it on another host yourself.

## Behaviour

- The integration keeps reconnecting (1 to 30 s backoff) while the server is unreachable. Paired devices are reported unavailable meanwhile, with the reason as their `last_error`.
- Unpairing a **SmartStart** device removes it from the provisioning list, also once it left by itself through a factory reset. Otherwise it would join again.

## Standalone

`run_controller(ZwaveController)` finds the stick and runs `zwave-js-server` for it, as the Hub does. Without Docker, run `zwave-js-server` yourself and pin it: `run_controller(ZwaveController, docker=False, pinned={"zwave": Endpoint("zwave", "zwave-js-ws", "ws://localhost:3000")})`. See [Standalone Mode](../device-integration/standalone.md#connecting-to-radios-and-services).
