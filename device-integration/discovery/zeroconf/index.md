# Zeroconf (mDNS / DNS-SD / Bonjour) Discovery

## `ZeroconfDiscoveryService`

Available as `self.dependencies.zeroconf_discovery_service`.

### `register`

```python
def register(
    listener: ZeroconfDiscoveryListener,
    services: set[str],
) -> Callable[[], None]: ...
```

| Arg        | Type                        | Description                                                          |
| ---------- | --------------------------- | -------------------------------------------------------------------- |
| `listener` | `ZeroconfDiscoveryListener` | Receives discovery events                                            |
| `services` | `set[str]`                  | Fully-qualified mDNS service type strings, e.g. `"_hap._tcp.local."` |

Returns a cancel closure — call it in `stop()` to deregister.

### `async_zeroconf`

```python
async_zeroconf: AsyncZeroconf | None
```

The underlying `AsyncZeroconf` instance, available after the service starts. Use only when you need low-level zeroconf access.

______________________________________________________________________

## `ZeroconfDiscoveryListener` (Protocol)

```python
class ZeroconfDiscoveryListener(Protocol):
    async def zeroconf_did_discover_service(
        self,
        zeroconf: ZeroconfDiscoveryService,
        info: ZeroconfDiscoveryInfo,
    ): ...

    async def zeroconf_did_update_service(
        self,
        zeroconf: ZeroconfDiscoveryService,
        info: ZeroconfDiscoveryInfo,
    ): ...

    async def zeroconf_did_remove_service(
        self,
        zeroconf: ZeroconfDiscoveryService,
        type_: str,
        name: str,
    ): ...
```

Note: `zeroconf_did_remove_service` fires on mDNS goodbye packets (TTL=0) or when a silent departure is confirmed: A/AAAA records expired and a follow-up probe got no response. Typical latency for silent departures is ~120 s (A/AAAA TTL). For faster detection, implement liveness checks at the pairing/connection layer.

______________________________________________________________________

## `ZeroconfDiscoveryInfo`

```python
@dataclass
class ZeroconfDiscoveryInfo:
    type_: str
    name: str
    server: str | None
    port: int | None
    addresses: list[bytes] | None
    parsed_addresses: list[str] | None
    weight: int | None
    priority: int | None
    properties: dict[bytes, bytes | None]
    decoded_properties: dict[str, str | None]
    text: bytes
    host_ttl: int | None
    other_ttl: int | None
    interface_index: int | None
```

Key fields:

| Field                | Type                         | Description                                                                 |
| -------------------- | ---------------------------- | --------------------------------------------------------------------------- |
| `type_`              | `str`                        | Fully qualified service type (e.g. `_hap._tcp.local.`)                      |
| `name`               | `str`                        | Fully qualified service name                                                |
| `server`             | `str \| None`                | Hostname of the service                                                     |
| `port`               | `int \| None`                | Port the service listens on                                                 |
| `parsed_addresses`   | `list[str] \| None`          | IP addresses as strings                                                     |
| `decoded_properties` | `dict[str, str \| None]`     | TXT record key-value pairs decoded to `str`; use this for most integrations |
| `properties`         | `dict[bytes, bytes \| None]` | Raw TXT record bytes                                                        |
| `text`               | `bytes`                      | Raw TXT record bytes (full)                                                 |
| `interface_index`    | `int \| None`                | IPv6 zone id / scope id                                                     |

`__eq__` excludes TTL fields — safe for change detection.

______________________________________________________________________

## Example

```python
# in Controller
...
async def start(self):
    self._cancels: set[Callable[[], None]] = set()
    cancel = self.dependencies.zeroconf_discovery_service.register(
        self,  # self implements ZeroconfDiscoveryListener
        {"_hap._tcp.local."},
    )
    self._cancels.add(cancel)

async def stop(self):
    for cancel in self._cancels:
        cancel()

# ZeroconfDiscoveryListener Implementation

async def zeroconf_did_discover_service(self, zeroconf: ZeroconfDiscoveryService, info: ZeroconfDiscoveryInfo):
    if discovery := self._mapper._map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.dependencies.output.controller_did_receive_discovery(self, discovery)

async def zeroconf_did_update_service(self, zeroconf: ZeroconfDiscoveryService, info: ZeroconfDiscoveryInfo):
    if discovery := self._mapper._map_to_discovery(info):
        self._discoveries[discovery.id] = discovery
        await self.dependencies.output.controller_did_update_discovery(self, discovery)

async def zeroconf_did_remove_service(self, zeroconf: ZeroconfDiscoveryService, type_: str, name: str):
    if discovery_id := self._mapper._name_to_id(name) and discovery_id in self._discoveries:
      self._discoveries.pop(discovery_id, None)
      await self.dependencies.output.controller_did_lose_discovery(self, discovery_id)
...
```
