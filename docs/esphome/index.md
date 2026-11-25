# ESPHome Components

[MajorDom-Systems/esphome-components](https://github.com/MajorDom-Systems/esphome-components) holds the [ESPHome](https://esphome.io) external components MajorDom devices are built with. They add what ESPHome does not have (yet); each is meant to go upstream, and is kept here until it does.

| Component | What it does |
|---|---|
| [`thread_provisioning`](thread-provisioning.md) | Gives a Thread node its network over BLE at runtime, so one image ships without one. |

## Use

Add the repository as an [external component source](https://esphome.io/components/external_components/), pinned to a release tag:

```yaml
external_components:
  - source: github://MajorDom-Systems/esphome-components@v0.1.0
    components: [thread_provisioning]
```

Each release is compiled in CI against the ESPHome version pinned in the repository's `requirements.txt`; newer ESPHome releases are picked up by Dependabot and compile-checked before they are merged.
