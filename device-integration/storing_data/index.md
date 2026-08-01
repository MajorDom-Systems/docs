# Storing Data

## integration_data

MajorDom's Device and Parameter schemas expose an `integration_data` field for storing protocol-specific state (pairing tokens, internal IDs, etc.). By default it is an untyped dict persisted as JSON.

Integrations can subclass Device/DeviceState and Parameter/ParameterState to declare a typed schema for that field — Hub will then handle (de-)serialization automatically before passing Device instance to Controller's methods or when saving to the database.

```python
# majordom_myintegration/models.py
from majordom_integration_sdk.schemas.base import Base
from majordom_integration_sdk.schemas.device import Device, DeviceState
from majordom_integration_sdk.schemas.parameter import Parameter, ParameterState

class MyDeviceIntegrationData(Base):
    pairing_token: str | None = None

class MyDevice(Device):
    integration_data: MyDeviceIntegrationData

class MyParameterState(ParameterState):
    integration_data: MyParameterIntegrationData
```

To make the Hub use these custom types, the integration's Controller must override `device_type` and `parameter_type`:

```python
@property
def device_type(self) -> type[MyDevice]:
    return MyDevice

@property
def parameter_type(self) -> type[MyParameter]:
    return MyParameter
```

The Hub will deserialize objects into these types before passing them to your implemented methods.

### Repository

Use `self.dependencies.make_device_repository` to read or persist devices:

```python
async with self.dependencies.make_device_repository() as repo:
    device = await repo.get(device_id, as_=MyDevice) # `as_=MyDevice` is optional but provides hassle-free deserialization

async with self.dependencies.make_device_repository() as repo:
    device.integration_data.some_field = new_value # assuming `MyDevice.integration_data` uses custom class with `some_field` present
    await repo.save(device)
```

## File Storage (`documents_folder`)

For files that cannot be stored in the database (e.g. a protocol's own SQLite DB, certificates, binary blobs), use `self.documents_folder`:

```python
path = self.documents_folder / "zigbee.db"
```

Resolves to a dedicated directory for this integration under the Hub's data root, created automatically on first write.
