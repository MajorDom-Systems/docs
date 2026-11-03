# Settings

Give the user options by declaring a pydantic model. The Hub turns it into a form in the app, stores the values, and hands them to your controller.

## Declaring settings

Declare the model as a nested `Settings` class, named as the controller's last type parameter:

```python
from pydantic import BaseModel, Field

from majordom_integration_sdk import AbstractController, Device, Parameter
from majordom_integration_sdk import SettingsExtraField as Extra


class AcmeController(AbstractController[Device, Parameter, "AcmeController.Settings"]):
    class Settings(BaseModel):
        poll_interval: int = Field(30, ge=5, le=3600, title="Poll interval, seconds")
        api_token: str = Field("", title="Cloud API token", json_schema_extra={Extra.write_only: True})
        firmware: str | None = Field(None, title="Bridge firmware", json_schema_extra={Extra.read_only: True})
```

The app builds the form from the model's JSON schema. So:

- Give every field a `title` and, where it helps, a `description`, in plain language for the user: what it is, and what an empty value does.
- Use pydantic constraints (`ge`, `le`, `Literal[...]`). The Hub validates every change against them.
- Give every field a default: the Hub creates the settings before the user opens the form.

Mark fields with `SettingsExtraField`, never a spelled-out keyword:

- `write_only`: the user sets it, and the Hub never shows it again (a secret). An update that leaves it out keeps it.
- `read_only`: your controller fills it in itself (`self.settings.firmware = "2.1"`). The user sees it but can't change it. It isn't stored.

## Reading settings

The validated instance is `self.settings`, typed by your model. Without a `Settings` class, it is `NoSettings`.

## Defaults are kept

The Hub stores the values the first time it reads the settings, defaults included. A `default_factory` runs once, and its result stays: that's how to generate a secret once per Hub, e.g. network keys.

```python
api_secret: str = Field(default_factory=lambda: secrets.token_hex(16), title="Secret", json_schema_extra={Extra.write_only: True})
```

It also means a default you change in a later release applies to new Hubs only.

## Settings of a service

A [`Service`](peripherals.md#tldr-bringing-a-docker-service) can have settings too. Pass the model as `settings=`, and use its fields in `compose` as `{settings.<field>}`:

```python
class ServerOptions(BaseModel):
    log_level: Literal["info", "debug"] = Field("info", title="Server log level")


Service(
    "acme-server",
    compose={"image": "…", "environment": {"LOG_LEVEL": "{settings.log_level}"}},
    settings=ServerOptions,
)
```

The user sees a service's settings next to the settings of every integration that uses it.

## Changing settings

The user changes settings in the app; the Hub validates and stores them, then applies them. A service is recreated. Your controller gets [`settings_did_change(before)`](controller.md#hooks): return `True` when you applied them in place, or leave the default (`False`) to be restarted.

In [standalone mode](standalone.md), pass them to the constructor, `AcmeController(platform, settings=AcmeController.Settings(poll_interval=10))`, or change them through the runtime: `await runtime.update_settings(runtime.peripheral("acme"), {"poll_interval": 10})`.

## Hub settings

Some settings belong to the whole Hub. They reach you as facts on `self.platform` (and `{platform.<fact>}` in a service's `compose`):

| Fact | Meaning |
|---|---|
| `platform.region` | where the Hub is used, for sub-GHz radios, named as Z-Wave JS names them: `Europe`, `USA`, … |
| `platform.wifi` | the Wi-Fi network to set new devices up on (`ssid`, `password`), or `None` |
| `platform.thread_dataset` | the active dataset of the Hub's Thread network, hex; learned from the border router, not set by the user |

When they change, your controller gets [`platform_facts_did_change(before)`](controller.md#hooks). Read `self.platform` each time you need a fact: a platform object you kept holds the old values.
