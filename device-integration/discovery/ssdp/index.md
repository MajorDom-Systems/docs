# SSDP / UPnP Discovery

## `SSDPDiscoveryService`

Available as `self.dependencies.ssdp_discovery_service`.

### `register`

```python
def register(
    self,
    listener: SSDPDiscoveryListener,
    search_target: str,
    mcast_group: str = "239.255.255.250",
    port: int = 1900,
) -> Callable[[], None]: ...
```

| Arg             | Type                    | Default             | Description                                |
| --------------- | ----------------------- | ------------------- | ------------------------------------------ |
| `listener`      | `SSDPDiscoveryListener` | required            | Receives discovery events.                 |
| `search_target` | `str`                   | required            | SSDP ST field. See common templates below. |
| `mcast_group`   | `str`                   | `"239.255.255.250"` | Multicast group. Change only if necessary. |
| `port`          | `int`                   | `1900`              | SSDP port. Change only if necessary.       |

Returns a cancel closure — call it in `stop()` to deregister.

**Common `search_target` values:**

| ST                                            | Discovers                     |
| --------------------------------------------- | ----------------------------- |
| `"upnp:rootdevice"`                           | All UPnP root devices         |
| `"ssdp:all"`                                  | All UPnP devices and services |
| `"urn:schemas-upnp-org:device:MediaServer:1"` | UPnP MediaServer devices      |
| `"uuid:<device-UUID>"`                        | A specific device by UUID     |

______________________________________________________________________

## `SSDPDiscoveryListener` (Protocol)

```python
class SSDPDiscoveryListener(Protocol):
    async def ssdp_did_discover_service(self, ssdp: SSDPDiscoveryService, info: SSDPDiscoveryInfo): ...
    async def ssdp_did_update_service(self, ssdp: SSDPDiscoveryService, info: SSDPDiscoveryInfo): ...
    async def ssdp_did_remove_service(self, ssdp: SSDPDiscoveryService, info: SSDPDiscoveryInfo): ...
```

`ssdp_did_remove_service` fires when a device sends a `ssdp:byebye` NOTIFY, or when a device fails to respond to several consecutive M-SEARCH bursts (controlled by `_missed_scans_evict`, default 3 missed scans).

______________________________________________________________________

## `SSDPDiscoveryInfo`

```python
@dataclass
class SSDPDiscoveryInfo:
    addr: str
    host: str | None
    search_target: str | None
    service_name: str | None        # USN (Unique Service Name)
    server: str | None
    cache_control: str | None
    location: str | None            # URL to the device description XML
    response: dict[str, str]        # full raw response headers
```

______________________________________________________________________

## Example

```python
# in Controller
...
async def start(self):
    self._cancels: set[Callable[[], None]] = set()
    cancel = self.dependencies.ssdp_discovery_service.register(
        self,  # self implements SSDPDiscoveryListener
        "urn:schemas-upnp-org:device:MediaServer:1",
    )
    self._cancels.add(cancel)

async def stop(self):
    for cancel in self._cancels:
        cancel()

# SSDPDiscoveryListener Implementation

async def ssdp_did_discover_service(self, ssdp: SSDPDiscoveryService, info: SSDPDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.dependencies.output.controller_did_receive_discovery(self, discovery)

async def ssdp_did_update_service(self, ssdp: SSDPDiscoveryService, info: SSDPDiscoveryInfo):
    if discovery := self._mapper.map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.dependencies.output.controller_did_update_discovery(self, discovery)

async def ssdp_did_remove_service(self, ssdp: SSDPDiscoveryService, info: SSDPDiscoveryInfo):
    discovery_id = self.device_uuid(info.service_name or info.addr)
    if discovery_id in self._discoveries:
        self._discoveries.pop(discovery_id)
        await self.dependencies.output.controller_did_lose_discovery(self, discovery_id)
...
```
