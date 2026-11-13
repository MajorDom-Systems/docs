# Example: a server and its controller

A complete, tested integration skeleton around a server: a TCP echo server stands in for your protocol's server
(zwave-js-server, a matter.js server). It shows what the [template](https://github.com/MajorDom-Systems/integration-template)
leaves as placeholders: bringing the server as a `Service`, binding the controller to it with a `Need`, settings on
both, and a controller that stays connected by itself through restarts and outages. Read
[Peripherals](peripherals.md) first; copy what fits.

## The server: `config.py`

```python
from majordom_integration_sdk import Endpoint, Service
from pydantic import BaseModel, Field

# EXAMPLE: a tiny TCP echo server standing in for your protocol's server. Replace it; pin yours by digest.
IMAGE = "istio/tcp-echo-server:1.3@sha256:782259608d5ce934e1a07ce4a3f2664934b6806d50430fd20b7bf429ea500272"


class ServerSettings(BaseModel):
    """What the user can set on the server. They go into its compose, so a change recreates its container: the
    controller loses its connection and reconnects."""

    # Give every field a default: the server is built with them before the user can enter any
    greeting: str = Field(
        "hello",
        min_length=1,  # the server needs one: an empty value would leave the argument out
        title="Greeting",
        description="What the server puts before every line it echoes.",
    )


def example_server() -> Service[ServerSettings]:
    """A new one per call: the runtime keeps its state on the instance it runs."""
    return Service(
        "example-server",
        provides=[Endpoint("example", "echo", "tcp://127.0.0.1:{ports.api}")],
        settings=ServerSettings,
        ports={"api": 9000},  # preferred: the runtime picks another one when it's taken
        compose={
            "image": IMAGE,
            # Make yours listen on 127.0.0.1 only (e.g. zwave-js-server's `--host 127.0.0.1`): the Hub reaches it over
            # loopback, and nothing guards it on the LAN. This echo server can't choose its address.
            "network_mode": "host",
            "command": ["{ports.api}", "{settings.greeting}"],  # listens on the port the runtime picked
        },
    )
```

A user setting of the server (`greeting`) goes into its compose, so changing it recreates the container: the
controller loses its connection and reconnects.

## The controller's needs and settings

```python
class ExampleController(AbstractController[Device, Parameter, "ExampleController.Settings"]):
    """Bridges the Example protocol into MajorDom."""

    # Shown to the user, and its identity: its slug is the key the integration's devices, settings and folder are
    # kept by. Never rename it once released.
    name = "Example"

    # What the controller connects to beyond the network, and what the user can set. The Hub runs
    # `example_server()`, which the package provides next to it, binds the need to it and hands over
    # its URL in `self.peripherals.endpoint("example")`; settings arrive validated in `self.settings`.
    # Declare everything external as a Need: radios, the SDK's typed BLE_ROUTER (never raw Bluetooth), ZEROCONF,
    # UPNP_SSDP (majordom_integration_sdk.capabilities) and the services you bring.
    # Leave them out if the protocol only uses the network.
    # See https://docs.majordom.io/device-integration/radios and .../settings.
    needs = [Need("example", ["echo"])]

    class Settings(BaseModel):
        # Give every field a default: the Hub builds the controller with them before the user can enter any
        server_name: str = Field(
            "MajorDom",
            pattern=r"^[^\r\n]+$",  # one line: it goes into the line protocol
            max_length=64,
            title="Server name",
            description="How the server introduces itself.",
        )

    _RECONNECT_DELAY = 1.0  # seconds, doubled after every attempt until a connection holds
    _RECONNECT_DELAY_MAX = 30.0
    _UNREACHABLE_AFTER = 15.0  # seconds away before the user is told
    # Seconds a connection must hold to end an outage (the runtime's stable run): drops in a row add up, so a server
    # that answers and drops every time is reported too
    _STABLE_CONNECTION = STABLE_RUN
    _ANSWER_TIMEOUT = 10.0  # seconds a server may take to answer a new connection
```

## Starting, stopping and the hooks

`start` connects once and raises if it can't (the Hub retries it), then leaves a task to keep the connection.
`stop` undoes all of it, also after a half-done `start`.

```python
    def __init__(self, platform: Platform, *, settings: Settings | None = None):
        super().__init__(platform, settings=settings)
        self._discoveries: dict[UUID, Discovery] = {}
        self._reconnect_delay = self._RECONNECT_DELAY  # kept across the drops of an outage: it grows through them
        # What start() sets up: stop() leaves them as here, also after a start that failed half-way
        self._writer: asyncio.StreamWriter | None = None  # to the server, while connected
        self._keeper: asyncio.Task[None] | None = None
        # e.g. self._cancel_zeroconf: Callable[[], None] | None = None

    @property
    def discoveries(self) -> dict[UUID, Discovery]:
        # Return the cached snapshot only — never scan here.
        return self._discoveries

    # Lifecycle -------------------------------------------------------------

    async def start(self):
        # Register with discovery (needed as peripherals), subscribe to protocol events, and reconcile the
        # state of already-paired devices here.
        # e.g. async with self.platform.device_repository(self) as repository: paired = await repository.get_all()
        # Then report every paired device that answers: the Hub marked them all unavailable when the integration
        # stopped. e.g. await self.output.controller_did_connect_device(self, physical_id=device.physical_id)
        # e.g. with ZEROCONF in `needs`:
        # self._cancel_zeroconf = self.peripherals.instance(ZEROCONF).register(self, {"_example._tcp.local."})
        reader = await self._connect()  # raising here has the Hub retry start()
        self._keeper = asyncio.create_task(self._stay_connected(reader))

    async def stop(self):
        # Cancel tasks and release every held resource, also after a start that failed half-way: the Hub stops it then
        # too, and starts the same object again later. Nothing in flight may take resources after it: a pairing that
        # finishes later is refused and undone (see pair_device).
        # e.g. if self._cancel_zeroconf:
        #     self._cancel_zeroconf()
        #     self._cancel_zeroconf = None
        if self._keeper:
            self._keeper.cancel()
            await asyncio.wait([self._keeper])  # unlike awaiting it, never raises (the keeper reports a crash itself)
            self._keeper = None
        self._disconnect()
        self._discoveries.clear()  # heard anew after the next start, which reports them again

    # Hooks: return True when applied in place, False to have the Hub restart the integration. The
    # defaults: settings_did_change and needed_peripheral_did_change (a need moved, or an optional one
    # appeared) restart it; platform_facts_did_change doesn't.

    async def settings_did_change(self, before: Settings) -> bool:
        if self.settings.server_name != before.server_name and self._writer:
            with contextlib.suppress(OSError):  # the server is away: the keeper hands it the name on reconnect
                await self._sync_with_server(self._writer)
        return True

    async def platform_facts_did_change(self, before: Platform) -> bool:
        # The server gets the region when the controller connects: let the Hub restart it for a new one
        return self.platform.region == before.region
```

## Staying connected

The server is recreated when its settings change and may crash at any time; nobody tells the controller. The keeper
task reconnects with a growing delay, tells the user only when the server stays away for a while, and counts a server
that answers and drops every time as one outage until a connection holds for `STABLE_RUN` seconds.

```python
    # Server ------------------------------------------------------------------

    async def _connect(self) -> asyncio.StreamReader:
        url = urlsplit(self.peripherals.endpoint("example").url)  # never build it yourself: the port may differ
        reader, self._writer = await asyncio.open_connection(url.hostname, url.port)
        await self._sync_with_server(self._writer)
        # Connected once it answers (here the echo of its name; yours may greet first). One that hangs up before (it
        # refused the client, a proxy without its backend) or keeps silent isn't back: a failed attempt.
        async with asyncio.timeout(self._ANSWER_TIMEOUT):  # TimeoutError is an OSError
            if not await reader.readline():
                raise ConnectionResetError("the server hung up before it answered")
        return reader

    def _disconnect(self):
        if self._writer:
            self._writer.close()
            self._writer = None

    async def _sync_with_server(self, writer: asyncio.StreamWriter):
        """Hands the server its configuration; on every (re)connect."""
        writer.write(f"name {self.settings.server_name}\n".encode())
        if region := self.platform.region:
            writer.write(f"region {region}\n".encode())
        await writer.drain()

    async def _stay_connected(self, reader: asyncio.StreamReader):
        """Reconnects whenever the server goes away (e.g. it was restarted) until stop() cancels it,
        so the integration heals by itself instead of being restarted by the Hub."""
        loop = asyncio.get_running_loop()
        lost_at: float | None = None  # when the outage began
        try:
            while True:
                connected_at = loop.time()
                await self._listen(reader)
                self._disconnect()
                # The devices behind it are out of reach now: e.g. controller_did_lose_device for each
                if lost_at is None or loop.time() - connected_at >= self._STABLE_CONNECTION:
                    lost_at = loop.time()  # a new outage, else the last one goes on
                    self._reconnect_delay = self._RECONNECT_DELAY
                reader = await self._reconnect(lost_at)
                # Back: e.g. controller_did_connect_device for each that answers again
        except Exception:  # a bug rather than an outage: the Hub restarts the integration, then gives up on it
            logger.exception(f"[{self.name}] stopped listening to the server")
            message = "The connection to the Example server broke unexpectedly."
            crashed = IntegrationError("crashed", message, is_still_running=False)
            await self.output.controller_did_encounter_error(self, crashed)

    async def _reconnect(self, lost_at: float) -> asyncio.StreamReader:
        """Tries again, less and less often, until the server is back. Tells the user only once it was away for a
        while: a server restarting on purpose (e.g. recreated with new settings) is usually back well before."""
        loop = asyncio.get_running_loop()
        is_reported = False
        while True:
            # Also before the first try: a drop soon after another one is reported at once
            if not is_reported and loop.time() - lost_at >= self._UNREACHABLE_AFTER:
                message = "Lost the connection to the Example server, reconnecting."
                lost = IntegrationError("server-unreachable", message)
                await self.output.controller_did_encounter_error(self, lost)
                is_reported = True
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._RECONNECT_DELAY_MAX)
            try:
                reader = await self._connect()
            except OSError as error:
                self._disconnect()  # a connection it hung up
                logger.info(f"[{self.name}] the server is not back yet: {error!r}")
            else:
                if is_reported:  # the devices work again, though the outage lasts until the connection holds
                    await self.output.controller_did_resolve_error(self, "server-unreachable")
                return reader

    async def _listen(self, reader: asyncio.StreamReader):
        """Reads the server's messages until it closes the connection."""
        with contextlib.suppress(OSError):
            while line := await reader.readline():
                # Turn protocol messages into events here: controller_did_receive_events(...)
                # Log and skip one you can't take: whatever raises here has the Hub restart the integration.
                logger.debug(f"[{self.name}] server: {line!r}")
```

## Testing it without the server

The tests run the controller against an in-process stand-in that echoes and records what it receives, and can go
away or hang up on every client:

```python
"""What the tests run the controller against, in place of the server the integration brings."""

import asyncio
import contextlib


class VirtualServer:
    """An in-process stand-in for `example_server()`: echoes and records the lines it receives, and can go away or hang
    up on every client, before or after it answers."""

    def __init__(self):
        self.port = 0
        self.lines: list[str] = []
        self.connections = 0
        self.is_hanging_up = False  # closes every connection before it answers, e.g. it refuses the client
        self.is_dropping = False  # closes every connection once it answered, e.g. it crashes on what follows
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()  # the connected ones

    async def start(self):
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]  # the same one again after a restart

    async def stop(self):
        for client in self._clients:
            client.close()
        self._clients.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def is_connected(self) -> bool:
        return bool(self._clients)

    async def send(self, line: bytes):
        for client in [*self._clients]:  # one may go while another drains
            client.write(line + b"\n")
            await client.drain()

    async def received(self, line: str):
        async with asyncio.timeout(2):
            while line not in self.lines:
                await asyncio.sleep(0.01)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.connections += 1
        self._clients.add(writer)
        try:
            with contextlib.suppress(ConnectionError):
                while not self.is_hanging_up and (line := await reader.readline()):
                    self.lines.append(line.decode().strip())
                    writer.write(line)
                    await writer.drain()
                    if self.is_dropping:
                        break
        finally:  # the client went: stop writing to it
            self._clients.discard(writer)
            writer.close()
```

Bind the controller's need to it by hand, as in library mode:

```python
@pytest.fixture
def controller(platform: Platform, server: VirtualServer, output: RecordingControllerOutput) -> ExampleController:
    controller = ExampleController(platform)
    controller.peripherals = Peripherals({"example": Endpoint("example", "echo", f"tcp://127.0.0.1:{server.port}")})
    controller.output = output
    return controller
```

One of the outage tests:

```python
async def test_reconnects_when_the_server_comes_back(
    controller: ExampleController,
    output: RecordingControllerOutput,
    server: VirtualServer,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(ExampleController, "_RECONNECT_DELAY", 0.01)
    monkeypatch.setattr(ExampleController, "_RECONNECT_DELAY_MAX", 0.04)
    monkeypatch.setattr(ExampleController, "_UNREACHABLE_AFTER", 0.05)
    await controller.start()
    await server.received("name MajorDom")

    await server.stop()
    await until(lambda: "server-unreachable" in output.errors)  # a few attempts failed while it's down
    server.lines.clear()
    await server.start()

    await server.received("name MajorDom")
    await until(lambda: not output.errors)  # resolved once connected again
    lost = IntegrationError("server-unreachable", "Lost the connection to the Example server, reconnecting.")
    assert output.error_log == [lost, "server-unreachable"]
    await controller.stop()
```
