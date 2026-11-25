# Peripherals Firmware

[MajorDom-Systems/firmware](https://github.com/MajorDom-Systems/firmware) holds the firmware for MajorDom peripherals and the third-party devices MajorDom supports: what each board is, which firmware it can run, and the builds themselves. CI builds every package from source and publishes it as a GitHub Release; a signed channel on GitHub Pages lists them for the Hub, the SDK and any other client.

## Browse the builds

<iframe
  src="https://majordom-systems.github.io/firmware/"
  title="MajorDom firmware"
  loading="lazy"
  style="width:100%;height:640px;border:1px solid var(--md-default-fg-color--lightest);border-radius:.2rem;margin-top:.5rem;">
</iframe>

<p>
  <a class="md-button md-button--primary" href="https://majordom-systems.github.io/firmware/" target="_blank">
    Open the firmware page ↗
  </a>
</p>

Pre-releases and builds for development boards are hidden until **Show dev** is ticked.

## Boards and packages

- A **board** is a piece of hardware: a MajorDom PCB or a supported stick. Its manifest says how to recognise it (USB ids and product names) and lists its **slots**, the radios on it, each with how the host reaches it (serial device, flow control, reset) and the firmware it can run.
- A **package** is one firmware build for one chip. It never names a board; slots list packages. Each package says which **protocol** it speaks, in the SDK's vocabulary, so the SDK can pick the driver:

| Protocol | Firmware |
|---|---|
| `ezsp` | Zigbee NCP (EmberZNet) |
| `spinel` | Thread RCP (OpenThread) |
| `silabs-cpc` | Multiprotocol RCP: Zigbee and Thread on one radio |
| `zwave-serial-api` | Z-Wave controller (Serial API) |

Package names read `<chip>-<app>[-<what makes it unique>]`, for example `mg26-multipan-pa04-pa05`. Third-party builds that are only mirrored (pointing at their upstream URL, never re-hosted) keep their upstream name, for example `skyconnect-zigbee`.

## The channel

| File | What it holds |
|---|---|
| [`v1/boards.json`](https://majordom-systems.github.io/firmware/v1/boards.json) | Every public board and its slots |
| [`v1/stable.json`](https://majordom-systems.github.io/firmware/v1/stable.json) | Builds promoted to stable |
| [`v1/dev.json`](https://majordom-systems.github.io/firmware/v1/dev.json) | Every build, pre-releases included; downgrades allowed |

`stable.json` and `dev.json` carry a [minisign](https://jedisct1.github.io/minisign/) signature next to them (`.minisig`) and expire after 90 days unless re-signed, so a stale or tampered copy is refused. Each entry gives the file URL, its size and sha256, the protocol and the serial settings. Verify by hand:

```bash
curl -sO https://majordom-systems.github.io/firmware/v1/stable.json
curl -sO https://majordom-systems.github.io/firmware/v1/stable.json.minisig
minisign -V -P RWTsJmUaNF5r45iUoM5IH5iytacQ0dF7Je13wg8L8dOdRuU8znTbNW7d -m stable.json
```

## How MajorDom uses it

The radios become peripherals: an integration asks for a capability such as `zigbee/ezsp`, and the Hub hands over whichever stick or soldered radio runs firmware speaking that protocol. See [Peripherals](../integrations/peripherals.md#radios).

The integration SDK bundles a copy of the channel as an offline fallback and, on start, replaces it with the live channel when its signatures verify. With it the SDK recognises a plugged-in stick, picks its driver by protocol, and knows which firmware it can be flashed with. On a MajorDom Hub, the radios wired on the board are described by `/etc/majordom/board.json`, generated from the board's manifest and published per board at `v1/<board>/board.json`.

## Flashing by hand

Silicon Labs radios take the `.gbl` file over their serial port with [universal-silabs-flasher](https://github.com/NabuCasa/universal-silabs-flasher). Stop whatever holds the port first, then:

```bash
universal-silabs-flasher --device /dev/ttyUSB0 flash --firmware mg26-multipan-pa04-pa05_1.0.0.gbl
```

Check the sha256 against the channel entry before flashing. Z-Wave controllers are updated through zwave-js (`firmware_update_otw`).

## Licensing

Silicon Labs firmware is under the Silicon Labs MSLA. The compiled binaries are published for MajorDom and eligible hardware; the Simplicity SDK, its tools and the build image are never redistributed. See the repository's [`NOTICE`](https://github.com/MajorDom-Systems/firmware/blob/develop/NOTICE).
