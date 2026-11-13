# Bluetooth (BLE) Discovery

!!! danger "Never access Bluetooth hardware directly"
    Never access Bluetooth hardware directly via bluez, bleak or other Python libraries, system services, or any other way. For Bluetooth discovery, always use `BLERouter` as described below. For the full BLE specification with other usage, e.g. pairing and controlling devices, see [Capabilities: Bluetooth LE](../capabilities/ble.md).

The router hears every Bluetooth radio the hub has. You tell it which devices you are interested in, and it calls your controller when one appears, changes its advertisement, or goes away.

## Example

Everything a controller needs for BLE discovery. Copy it and change the three numbered lines:

```python
from uuid import UUID

from majordom_integration_sdk import AbstractController, Device, Discovery, Parameter, Platform
from majordom_integration_sdk.capabilities import BLE_ROUTER, BLEDiscoveryInfo, BLEMatcher, BLERouter
from majordom_integration_sdk.schemas import CredentialsOption, CredentialsType

# 1. Which devices to hear about: here, everything advertising this service UUID
MATCHERS = [BLEMatcher(service_uuid=UUID("0000fd00-0000-1000-8000-00805f9b34fb"))]


class AcmeController(AbstractController[Device, Parameter]):
    needs = [BLE_ROUTER]  # the Hub hands the router over in self.peripherals

    def __init__(self, platform: Platform, *, settings=None):
        super().__init__(platform, settings=settings)
        self._discoveries: dict[UUID, Discovery] = {}

    async def start(self):
        ble = self.peripherals.instance(BLE_ROUTER)
        self._cancel_ble = ble.register(self, MATCHERS)

    async def stop(self):
        self._cancel_ble()

    @property
    def discoveries(self) -> dict[UUID, Discovery]:
        return self._discoveries.copy()

    # BLEDiscoveryListener: called by the router

    async def ble_did_discover_device(self, ble: BLERouter, info: BLEDiscoveryInfo):
        discovery = self._to_discovery(info)
        self._discoveries[discovery.id] = discovery
        await self.output.controller_did_receive_discovery(self, discovery)

    async def ble_did_update_device(self, ble: BLERouter, info: BLEDiscoveryInfo):
        discovery = self._to_discovery(info)
        self._discoveries[discovery.id] = discovery
        await self.output.controller_did_update_discovery(self, discovery)

    async def ble_did_remove_device(self, ble: BLERouter, info: BLEDiscoveryInfo):
        discovery_id = self._discovery_id(info)
        if self._discoveries.pop(discovery_id, None):
            await self.output.controller_did_lose_discovery(self, discovery_id)

    def _discovery_id(self, info: BLEDiscoveryInfo) -> UUID:
        # 2. A stable id from the advertisement's content, e.g. a serial number in the manufacturer data
        serial = info.advertisement.manufacturer_data[0xFFFF].hex()
        return self.device_uuid(serial)

    def _to_discovery(self, info: BLEDiscoveryInfo) -> Discovery:
        return Discovery(
            id=self._discovery_id(info),
            integration=self.key,
            expected_credentials_options=[CredentialsOption(type=CredentialsType.none)],
            transport="BLE",
            device_manufacturer="Acme",  # 3. What the user sees
            device_name=info.advertisement.local_name or "Acme sensor",
            device_category=None,
            device_icon=None,
        )

    # pair_device, send_command and the rest: see Implementing a Controller
```

!!! warning "Don't build ids from the address"
    Many devices rotate their Bluetooth address, and each radio may report a different one. Derive the discovery id from the advertisement's content: a serial number, a MAC address inside the manufacturer data, Matter's discriminator with its vendor and product ids.

If your integration also works without Bluetooth, make the need optional and check for `None`:

```python
needs = [BLE_ROUTER(is_required=False)]

async def start(self):
    ble = self.peripherals.instance(BLE_ROUTER)  # None on a hub without Bluetooth
    self._cancel_ble = ble.register(self, MATCHERS) if ble else None
```

## Matchers

A listener hears about a device when it matches any of its matchers. A plain `UUID` matches that service. In a `BLEMatcher`, every field that is set must match:

| Field | Matches |
|---|---|
| `service_uuid` | a service UUID, advertised as a service or in the service data |
| `service_data_uuid` | a UUID in the service data only |
| `manufacturer_id` | a company id in the manufacturer data, e.g. `0x004C` for Apple |
| `manufacturer_data_start` | the first bytes of that manufacturer data (with `manufacturer_id`) |
| `local_name_prefix` | the start of the advertised name |

## Events

| Callback | Called when |
|---|---|
| `ble_did_discover_device` | a matching device is heard for the first time; devices heard before you registered count as new |
| `ble_did_update_device` | its advertisement changed (name, service UUIDs, manufacturer or service data); signal strength alone doesn't count |
| `ble_did_remove_device` | no radio has heard it for about 11 seconds |

`info.device` is bleak's `BLEDevice` (`.address`, `.name`); `info.advertisement` is bleak's `AdvertisementData`; `info.rssi` is the signal of the radio that hears it best.

To connect to a discovered device, see [Capabilities: Bluetooth LE](../capabilities/ble.md).

## Active scanning in a pairing window

Radios scan passively: they hear every advertisement, but many devices send their name only when asked. While the user is pairing, ask for an active scan:

```python
async def start_pairing_window(self, duration_sec: int, credentials: ProvidedCredentials | None = None):
    await self.peripherals.instance(BLE_ROUTER).scan_actively(duration_sec)
```
