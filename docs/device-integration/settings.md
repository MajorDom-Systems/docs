# Settings

Give the user options by declaring a pydantic model. The Hub turns it into a form in the app, stores the values, and hands them to your controller.

## Declaring settings

Set the model as the controller's `settings` class attribute ([`controller.py`](https://github.com/MajorDom-Systems/integration-zigbee/tree/master/majordom_zigbee/controller.py)):

```python
from pydantic import BaseModel, Field

class ZigBeeSettings(BaseModel):
    channel: int | None = Field(None, ge=11, le=26, title="Channel", description="Empty picks one when forming.")
    pan_id: int | None = Field(None, ge=0, le=0xFFFE, title="PAN ID", description="Empty generates one when forming.")
    extended_pan_id: str | None = Field(
        None, title="Extended PAN ID", description="Like dd:dd:dd:dd:dd:dd:dd:dd. Empty generates one when forming."
    )
    network_key: str | None = Field(None, title="Network key", description="32 hex digits. Empty generates one.")
    tx_power: int | None = Field(None, title="Transmit power, dBm", description="Empty uses the radio default.")


class ZigBeeController(AbstractController):
    needs = [Need("zigbee", ZIGPY_DIALECTS)]
    settings = ZigBeeSettings
```

The app builds the form from the model's JSON schema (`model_json_schema()`). So:

- Give every field a `title` and, where it helps, a `description`, in plain language for the user: what it is, and what an empty value does. Not the field name, not protocol jargon.
- Use pydantic constraints (`ge`, `le`, `Literal[...]`). The Hub validates every change against them.
- Give every field a default. The Hub creates the settings before the user has opened the form.

## Reading settings

The validated instance arrives in `platform.settings`:

```python
async def start(self):
    settings = cast(ZigBeeSettings, self.platform.settings or ZigBeeSettings())
```

The fallback covers library mode, where the caller may pass no settings.

## Defaults are kept

The Hub stores the values the first time it reads the settings, defaults included. A `default_factory` runs once and its result stays. That's how Z-Wave generates its network keys once per hub ([`config.py`](https://github.com/MajorDom-Systems/integration-zwave/tree/master/majordom_zwave/config.py)):

```python
def _key() -> str:
    return secrets.token_hex(16).upper()


class ZwaveNetwork(BaseModel):
    """Security keys of the Z-Wave network, generated once. Back them up: without them, securely
    included devices have to be re-included on a new controller."""

    s0_legacy: str = Field(default_factory=_key, title="S0 Legacy key")
    s2_unauthenticated: str = Field(default_factory=_key, title="S2 Unauthenticated key")
    ...
```

It also means a default you change in a later release applies to new hubs only.

## Settings of a service

A [`Service`](radios.md#bringing-your-own-service) can have settings too. Reach them in its `compose` through `{settings.<field>}`:

```python
ZWAVE_JS_SERVER = Service(
    "zwave-js-server",
    needs=[Need("zwave", ["serial-api"])],
    provides=[Endpoint("zwave", "zwave-js-ws", "ws://127.0.0.1:3000")],
    settings=ZwaveNetwork,
    compose={
        ...
        "environment": {
            "S0_LEGACY_KEY": "{settings.s0_legacy}",
            ...
            "RF_REGION": "{context.region}",
        },
    },
)
```

The user sees a service's settings on the screen of every integration that uses it, next to the integration's own. The Z-Wave screen shows the network keys; on a multi-PAN stick, the Zigbee screen also shows the Thread network settings of the `silabs-multiprotocol` service.

## Changing settings

The user changes settings in the app. The Hub validates the new values against the model, stores them, and applies them: a service's settings by recreating its container, the integration's own through [`settings_did_change()`](controller.md#settings_did_changebefore). Return `True` from it when applied in place; the default (`False`) has the Hub restart the integration.

In library mode, change them through the runtime:

```python
await runtime.update_settings("zigbee", {"tx_power": -20})
```

## Hub settings

Some settings belong to the whole hub (scope `hub`). Integrations see them through `platform.context`, services through `{context.<field>}`.

| Setting | Meaning | Reaches you as |
|---|---|---|
| `region` | Where the hub is used, for sub-GHz radios. Named as Z-Wave JS names them: `Europe`, `USA`, `Australia/New Zealand`, `Hong Kong`, `India`, `Israel`, `Russia`, `China`, `Japan`, `Korea`, `USA (Long Range)`, `Europe (Long Range)` | `context.region` |
| `wifi` | Saved Wi-Fi networks to set devices up on | — |
| `wifi_ssid` | Which saved network new devices go on; empty uses the hub's own network | `context.wifi` |
| `firmware` | Radio firmware the user may switch sticks to: `stable` (the default) offers verified builds only, `dev` every known build | — |

`context.thread_dataset` isn't a setting: the Hub learns it from the border router in use.
