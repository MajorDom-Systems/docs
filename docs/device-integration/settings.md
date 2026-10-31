# Settings

Give the user options by declaring a pydantic model. The Hub turns it into a form in the app, stores the values, and hands them to your controller.

## Declaring settings

Declare the model as a nested `Settings` class, named as the controller's last type parameter ([`controller.py`](https://github.com/MajorDom-Systems/integration-zigbee/tree/develop/majordom_zigbee/controller.py)):

```python
from majordom_integration_sdk import SettingsExtraField as Extra
from pydantic import BaseModel, Field

class ZigBeeController(AbstractController[ZBDevice, ZBParameter, "ZigBeeController.Settings"]):
    class Settings(BaseModel):
        # filled in once the network forms: the user sees them, never sets them
        channel: int | None = Field(None, title="Channel", json_schema_extra={Extra.read_only: True})
        pan_id: str | None = Field(None, title="PAN ID", json_schema_extra={Extra.read_only: True})
        tx_power: int | None = Field(None, ge=-10, le=20, title="Transmit power, dBm", description="Empty uses the radio default.")
```

The app builds the form from the model's JSON schema (`model_json_schema()`). So:

- Give every field a `title` and, where it helps, a `description`, in plain language for the user: what it is, and what an empty value does. Not the field name, not protocol jargon.
- Use pydantic constraints (`ge`, `le`, `Literal[...]`). The Hub validates every change against them.
- Give every field a default. The Hub creates the settings before the user has opened the form.

Mark fields with `SettingsExtraField`, never a spelled-out keyword:

- `read_only`: the peripheral fills it in itself (`self.settings.channel = 25`). The user sees it; an update to another value is refused. It is never stored.
- `write_only`: the user sets it, and the Hub never reads it back (a secret). An update that leaves it out keeps it.

## Reading settings

The validated instance is `self.settings`, typed by your model. In library mode, pass them to the constructor: `ZigBeeController(platform, settings=ZigBeeController.Settings(tx_power=10))`; without, the defaults apply.

## Defaults are kept

The Hub stores the values the first time it reads the settings, defaults included. A `default_factory` runs once and its result stays. That's how Z-Wave generates its network keys once per hub ([`config.py`](https://github.com/MajorDom-Systems/integration-zwave/tree/develop/majordom_zwave/config.py)):

```python
def _key() -> str:
    return secrets.token_hex(16).upper()


class ZwaveNetwork(BaseModel):
    """Security keys of the Z-Wave network, generated once. Back them up: without them, securely
    included devices have to be re-included on a new controller."""

    # write-only: the Hub never shows them, and an update without them keeps them
    s0_legacy: str = Field(default_factory=_key, title="S0 Legacy key", json_schema_extra={Extra.write_only: True})
    s2_unauthenticated: str = Field(default_factory=_key, title="S2 Unauthenticated key", json_schema_extra={Extra.write_only: True})
    ...
```

It also means a default you change in a later release applies to new hubs only.

## Settings of a service

A [`Service`](radios.md#bringing-your-own-service) can have settings too. Reach them in its `compose` through `{settings.<field>}`:

```python
Service(
    "zwave-js-server",
    needs=[Need("zwave", ["serial-api"])],
    provides=[Endpoint("zwave", "zwave-js-ws", "ws://127.0.0.1:{ports.api}")],
    ports={"api": 3000},
    settings=ZwaveNetwork,
    compose={
        ...
        "environment": {
            "S0_LEGACY_KEY": "{settings.s0_legacy}",
            ...
            "RF_REGION": "{platform.region}",
        },
    },
)
```

The user sees a service's settings on the screen of every integration that uses it, next to the integration's own. The Z-Wave screen shows the network keys; on a multi-PAN stick, the Zigbee screen also shows the Thread network settings of the `silabs-multiprotocol` service.

## Changing settings

The user changes settings in the app. The Hub validates the new values against the model, stores them, and applies them: a service's settings by recreating its container, the integration's own through [`settings_did_change()`](controller.md#hooks). Return `True` from it when applied in place; the default (`False`) restarts the integration.

In library mode, change them through the runtime:

```python
await runtime.update_settings(runtime.peripheral("zigbee"), {"tx_power": -20})
```

## Hub settings

Some settings belong to the whole hub (scope `hub`). The Hub turns them into platform facts: integrations read `self.platform.<fact>`, services `{platform.<fact>}`.

| Setting | Meaning | Reaches you as |
|---|---|---|
| `region` | Where the hub is used, for sub-GHz radios. Named as Z-Wave JS names them: `Europe`, `USA`, `Australia/New Zealand`, `Hong Kong`, `India`, `Israel`, `Russia`, `China`, `Japan`, `Korea`, `USA (Long Range)`, `Europe (Long Range)` | `platform.region` |
| `wifi` | Saved Wi-Fi networks to set devices up on | — |
| `wifi_ssid` | Which saved network new devices go on; empty uses the hub's own network | `platform.wifi` |
| `firmware` | Radio firmware the user may switch sticks to: `stable` (the default) offers verified builds only, `dev` every known build | — |

`platform.thread_dataset` isn't a setting: the Hub learns it from the border router in use. A change of facts calls [`platform_facts_did_change()`](controller.md#hooks).
