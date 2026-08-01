# Data Models Reference

## Pairing

```python
class CredentialsType(str, Enum):
    code = "code"      # pin, e.g. 123-45-678 (HomeKit) or 1234-123-1234 (Matter)
    secret = "secret"  # e.g. AES key like in ESPHome
    qr = "qr"          # raw QR data
    none = "none"

    def with_mask(self, code_mask: str) -> CredentialsType:
        """
        mask format: D as digit placeholder, other symbols like dashes remain unchanged,
        e.g. "DDD-DD-DDD" for "123-45-678"
        """
        self.code_mask = code_mask
        return self

type CredentialsValue = str

class ProvidedCredentials(Base):
    type: CredentialsType
    value: CredentialsValue | None = None

class Discovery(Base):
    # technical
    id: UUID
    integration: NonEmptyStr
    expected_credentials_options: list[CredentialsType]
    expiration: datetime | None = None
    # for UX
    transport: NonEmptyStr
    device_manufacturer: str | None
    device_name: NonEmptyStr
    device_category: str | None
    device_icon: str | None
    last_error: str | None = None  # set by the integration on failure, cleared (None) on recovery
```

A discovery advertises every credentials type it can actually be paired with — `expected_credentials_options` — since a device can support more than one simultaneously (e.g. a Matter device with both a QR code and a manual pairing code). List every option the device supports, in the order you'd like the app to prefer them.

Pairing requests then send back `ProvidedCredentials`, pairing the actual value with which type it is, instead of a bare string. **Your `pair_device()` must validate `credentials.type` is one of `discovery.expected_credentials_options` before using it** — don't trust `discovery.credentials` from whatever your own discovery-time heuristic guessed; validate against what the caller explicitly asserts.

## Device

```python
class DeviceInfo(DevicePatch):
    id: UUID
    name: str
    note: str = ""
    icon: str | None = None
    category: str | None = None
    room_id: UUID
    transport: str
    integration: str
    manufacturer: str | None
    last_seen: datetime | None = None
    available: bool = False
    last_error: str | None = None  # persisted; set by the integration on failure, cleared (None) on recovery
    main_parameter: UUID | None = None  # for the tap action on the room view, toggle in most cases

class Device(DeviceInfo):
    integration_data: SerializeAsAny[dict | Base] = Field(default_factory=Base)

class DeviceState(DeviceInfo):
    parameters: list[ParameterState]
```

## Parameter

```python
class ParameterDataType(StrEnum):
    none = "none"        # e.g. button
    bool = "bool"
    integer = "integer"
    decimal = "decimal"  # python float
    enum = "enum"        # integer with string representation
    string = "string"
    struct = "struct"    # multi-field object (e.g. command arguments); see "Commands with arguments"
    data = "data"        # binary data, base64 encoded at high level

class ParameterUnit(StrEnum):
    plain = "plain"
    percentage = "percentage"
    second = "second"
    hertz = "hertz"
    kilogram = "kilogram"
    arcdegree = "arcdegree"
    meters = "meters"
    mps = "mps"      # meters per second
    mps2 = "mps2"    # meters per second squared
    rpm = "rpm"
    newton = "newton"
    joule = "joule"
    watt = "watt"
    celsius = "celsius"
    kelvin = "kelvin"
    volt = "volt"
    ampere = "ampere"
    lux = "lux"
    pascal = "pascal"
    ppm = "ppm"      # parts per million, air quality
    bytes = "bytes"
    bps = "bps"      # bytes per second

class ParameterRole(StrEnum):
    sensor = 'sensor'   # read-only
    control = 'control' # read-write
    event = 'event'     # fire-and-forget


class ParameterVisibility(StrEnum):
    user = "user"  # main, everyday interaction, device screen widgets (on/off, brightness, volume)
    setting = "setting"  # user-configurable but behind am extra "settings"/"advanced" tap: configured once and rarely touched again; or diagnostic readings (RSSI, firmware version)
    system = "system"  # hidden under-the-hood wirings; not visible to the user

# Generic over its value type V — value, valid_values keys, and default_value all share V
# (an int parameter has int labels and an int default; a str parameter is str throughout).
class Parameter[V](UUIdentifable):
    id: UUID
    name: str
    description: str | None = None   # manufacturer-provided, read-only
    note: str | None = None          # user-editable, MajorDom-side only
    data_type: ParameterDataType
    unit: ParameterUnit = ParameterUnit.plain
    role: ParameterRole
    visibility: ParameterVisibility
    min_value: int | float | None = None
    max_value: int | float | None = None
    min_step: int | float | None = None       # smallest increment for a numeric parameter
    valid_values: dict[V, str] | None = None  # allowed values → labels; for enums (numbers: use min/max/step)
    fields: list["Parameter"] | None = None   # sub-parameters for data_type=struct (e.g. command args)
    default_value: set[V] | V | None = None   # main-parameter tap value(s): one = button, a set = cycle
    integration_data: Any                     # protocol-specific payload, opaque to the Hub

    @property
    def can_be_main_parameter(self) -> bool:
        return self.visibility == ParameterVisibility.user and bool(
            self.data_type in (ParameterDataType.bool, ParameterDataType.none)
            or self.default_value is not None
            or self.valid_values
        )

class ParameterState[V](Parameter[V]):
    value: V | None = None   # pythonic value (int/bool/str/float/dict/...), not bytes
```

### `main_parameter` and `default_value`

`Device.main_parameter` points at the one `Parameter` behind the room-tile tap (a toggle in most cases — e.g. `OnOff` for a light, not `Brightness`). A parameter is eligible (`can_be_main_parameter`) when it's `user`-visible and a tap does something meaningful: a `bool` or `none` command inherently, an `enum` through its `valid_values`, or — for any data type — a `default_value`.

`default_value` is what makes an arbitrary parameter tappable (any data type) and curates what a tap sends — set it to one value for a button, or a set for a cycle (e.g. brightness `{0, 80}` so a dimmer taps like an on/off switch). It shares the parameter's value type `V`. (`valid_values` only *describes* a parameter's allowed values and their labels — it doesn't carry the tap value.)

See [Parameter UX](https://docs.majordom.io/device-integration/parameter-ux/#the-one-tap-main-parameter) for how each case behaves on tap and how to pick the main parameter and good visibility.

### Commands with arguments

Some integrations (e.g. Matter) expose commands that take a list of arguments — for those, the command itself is modeled as a `Parameter` and each of its arguments as a nested `Parameter` in `fields`: **command = parameter, argument = sub-parameter**. This is a convention on top of the generic schema, not a separate concept. If your integration's commands don't take structured arguments, you leave `fields` unset.
