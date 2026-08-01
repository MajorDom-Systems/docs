"""MajorDom Hub — interactive module-map generator.

Run:  python docs/architecture/module_map.py
Emits: module-map.html (self-contained, interactive) + hub.svg alongside it.

All node/edge metadata are the hand-maintained dicts below, verified against the
Hub + integration-SDK + integration sources. Layout is a hand-computed concentric
ring layout (no graphviz dependency).
"""
import math, html, json

FILL={'core':'#e3e7ee','server':'#e1e5fb','automation':'#d7f0e8','devctl':'#f7e7cf',
'sdk':'#e9e3f8','integrations':'#f0e0e0','providers':'#e6efd9','cloud':'#dce9f7',
'hardware':'#eae7dc','repositories':'#f6ecd0','model':'#ece2f7','utils':'#e3e7ee'}
BORD={'core':'#8a93a2','server':'#8791e6','automation':'#3fae86','devctl':'#c98a2f',
'sdk':'#8a6fbf','integrations':'#c25f5f','providers':'#7fa05a','cloud':'#5aa9e0',
'hardware':'#a99e86','repositories':'#c98a2f','model':'#8a6fbf','utils':'#8a93a2'}
LABEL={'core':'core','server':'server / api','automation':'automation','devctl':'device control',
'sdk':'integration SDK','integrations':'integrations','providers':'providers','cloud':'cloud / ws client',
'hardware':'hardware','repositories':'repositories','model':'domain model','utils':'utils'}

# n(): inp = list of (declared_by, [methods]) groups ; out = output-delegate ports ; deps = injected dependencies
def n(id,label,domain,kind,base='—',impl=None,uses=None,inp=None,out=None,deps=None,pname=None):
    return {'id':id,'label':label,'domain':domain,'kind':kind,'base':base,'impl':impl or [],'uses':uses or [],
            'inp':inp or [],'out':out or [],'deps':deps or [],'pname':pname}
N=[
 n('coord','Coordinator','core','class · composition root',impl=['ControllerOutput'],
   inp=[['ControllerOutput',['controller_did_receive_events(events)','controller_did_receive_discovery / _update_discovery / _lose_discovery','controller_did_connect_device / _lose_device','controller_did_encounter_error / _emit_notification']],
        ['own',['start() / stop()','on_hub_initialized() · factory_reset() · reconnect_cloud()']]],
   out=['ws_sender.send_*: WsMessageSenderRelay   (→ app / cloud)'],
   deps=['controller_service: RelayController','automation_service: AutomationService','service_manager: ServiceManager','event_bus: EventBusImpl','(builds & owns every Service)']),
 n('main','__main__ · CLI','core','module (Typer)',
   inp=[['own',['run(shell, virtual, dev, reload, reset)']]],
   deps=['coordinator: Coordinator   (builds & runs)']),
 n('config','config · Settings','core','pydantic BaseSettings','BaseSettings',
   inp=[['own',['Settings() fields: enable/disable_services, host, port','db_url · db_async_url · matter_server_url · zigbee_device_path','secret_key / public_key / tokens']]]),
 n('svcmgr','ServiceManager','core','class',
   inp=[['own',['register(real, mock=None) -> ServiceProxy[T]','start_all() / stop_all() / start(name) / stop(name) / restart(name)','enable(name) / disable(name)']]],
   out=['proxies: ServiceProxy[T]   (real ⇄ null-object)'],
   deps=['ServiceOverride (DB) via create_async_session']),
 n('serversvc','ServerService','server','class · Service','—',impl=['Service'],
   inp=[['Service',['start(): run app in uvicorn.Server.serve() task','stop(): server.should_exit = True']]],
   deps=['app: FastAPI   (imported singleton)','coordinator + ws_* injected into app.state']),
 n('endpoints','endpoints /api/v1','server','FastAPI routers',
   inp=[['own',['REST routes: house·hub·room·device·scene·automation·services','each guarded by Depends(validate_access)']]],
   deps=['(Depends) DeviceProvider · HubProvider · RoomManager','(Depends) Automation/SceneManager · House/Hub/DeviceRepository']),
 n('deps','dependencies (DI)','server','FastAPI providers','—',uses=['DeviceRepositoryProtocol'],
   inp=[['own',['get_async_session() -> AsyncSession','device_repository() / device_provider() / hub_provider() / rooms_manager()','validate_access(raw_token, session) / auth_if_initialized()']]],
   deps=['session: AsyncSession   (→ utils.create_async_session)','constructs Repositories / Providers / Managers per request']),
 n('wsend','ws/user endpoint','server','WebSocket route',
   inp=[['own',['websocket_endpoint(ws, Authorization): receive_text loop','manual Bearer auth (UserToken) — close 4001 on fail']]],
   deps=['message_handler: WsMessageHandler','connection_manager: WsConnectionManager']),
 n('wsdocs','ws_docs','server','module',
   inp=[['own',['custom_openapi(app) / add_ws_message_endpoints()','SuperWSApiRouteWrapper (WS route → OpenAPI path)']]]),
 n('autosvc','AutomationService','automation','class · bus observer','—',impl=['EventBusObserver'],
   inp=[['EventBusObserver',['event_bus_did_receive_event(bus, event)']],
        ['own',['update_automation(a) / update_scene(s)','add_condition_checker(c) / add_action_handler(h)','start() / stop()']]],
   deps=['event_bus: EventBus   (add_observer(self))','_condition_checkers: dict[type, _ConditionChecker]','_action_handlers: dict[type, _ActionHandler]','_scene_manager: SceneManager']),
 n('eventbus','EventBusImpl','automation','class','—',impl=['EventBus'],pname='EventBus',
   inp=[['EventBus',['add_observer(o) / remove_observer(o)','publish(event) — fan out via asyncio.create_task']]],
   out=['_observers: set[EventBusObserver]   (calls event_bus_did_receive_event)']),
 n('ticker','MinuteTickerService','automation','class · Service','—',impl=['Service'],
   inp=[['Service',['start() / stop()']]],
   out=['on_event: Callable   (→ EventBus.publish(MinuteTickEvent))']),
 n('ckdev','DeviceParameterChecker','automation','class : _RuleConditionChecker (ABC)','_RuleConditionChecker',uses=['DeviceRepositoryProtocol'],
   inp=[['_ConditionChecker',['is_match(condition, event) -> bool / is_set(condition) -> bool','get_condition_type() -> DeviceParameterCondition']],
        ['own (overrides)',['_is_match: event matches device_id + parameter_id + rule','_is_set: read current ParameterState']]],
   deps=['make_device_repository(): DeviceRepository']),
 n('ckroom','RoomUnitChecker','automation','class : _RuleConditionChecker (ABC)','_RuleConditionChecker',uses=['DeviceRepositoryProtocol'],
   inp=[['_ConditionChecker',['is_match / is_set','get_condition_type() -> RoomUnitCondition']],
        ['own (overrides)',['_is_set: query all devices in the room by ParameterUnit']]],
   deps=['make_device_repository(): DeviceRepository']),
 n('ckcron','CronChecker','automation','class : _ConditionChecker (ABC)','_ConditionChecker',
   inp=[['_ConditionChecker',['is_match / is_set','get_condition_type() -> CronCondition']],
        ['own (overrides)',['_is_match: MinuteTickEvent datetime vs cron (cron_validator)']]]),
 n('cktime','TimeIntervalChecker','automation','class : _ConditionChecker (ABC)','_ConditionChecker',
   inp=[['_ConditionChecker',['is_match / is_set','get_condition_type() -> TimeIntervalCondition']],
        ['own (overrides)',['_is_match: MinuteTickEvent time within start–end window']]]),
 n('hdev','DeviceActionHandler','automation','class : _ActionHandler (ABC)','_ActionHandler',
   inp=[['_ActionHandler',['async execute(action)','get_action_type() -> DeviceAction']]],
   out=['execute_device_action: Callable   (→ RelayController.send_command)']),
 n('hfunc','FunctionActionHandler','automation','class : _ActionHandler (ABC)','_ActionHandler',
   inp=[['_ActionHandler',['async execute(action)','get_action_type() -> FunctionAction']],
        ['own',['runs action.function (asyncer.asyncify when sync)']]]),
 n('htext','TextActionHandler','automation','class : _ActionHandler (ABC)','_ActionHandler',
   inp=[['_ActionHandler',['async execute(action)','get_action_type() -> TextAction']],
        ['own',['stub — logs a warning (TODO: "Archie" TTS/notify)']]]),
 n('automan','Automation/SceneManager','automation','YamlManager[Input, Model] subclass','YamlManager[I,M]',
   inp=[['YamlManager',['get(id) / get_all() / save(input) -> model / delete(id)']]],
   out=['on_save: Callable   (→ AutomationService.update_automation / update_scene)'],
   deps=['directory: Path   (yaml files)']),
 n('relay','RelayController','devctl','class · domain boundary','—',impl=['ControllerOutput'],uses=['DeviceRepositoryProtocol'],
   inp=[['ControllerOutput',['controller_did_receive_events(events)   ← from child controllers','controller_did_receive_discovery / _update / _lose_discovery','controller_did_connect_device / _lose_device','controller_did_encounter_error / _emit_notification']],
        ['own',['send_command(command)   ◂ handlers · WsMessageHandler','pair_device(discovery, credentials) / unpair / identify / fetch','get_discoveries() / get_discovery(id) / ignore_discovery(id)','start_pairing_window(sec) / add_controller(c) / start() / stop()']]],
   out=['dependencies.output: ControllerOutput   (→ Coordinator)'],
   deps=['dependencies.make_device_repository(): DeviceRepositoryProtocol   (→ DeviceRepository, scoped)','_controllers: dict[str, AbstractController]   (→ Matter/Zigbee/HomeKit)','_ignored_repo: IgnoredDiscoveryRepository']),
 n('devprov','DeviceProvider','providers','class · nested Dependencies',
   inp=[['own',['create_device(DeviceCreate) / pair_existing_device(DevicePair)','update_device(id, DevicePatch) / delete_device(id, soft)','get_discoveries(include_ignored) / ignore_discovery(id) / start_pairing_window(sec)']]],
   deps=['dependencies.device_repository: DeviceRepository','dependencies.relay_controller: RelayController']),
 n('ignrepo','IgnoredDiscoveryRepository','devctl','class · file-backed',
   inp=[['own',['load() -> set[UUID]','save(ids: set[UUID])']]],
   deps=['path: Path   (JSON on disk)']),
 n('absctrl','AbstractController','sdk','abstract class · Generic[TDevice, TParameter]','ABC',uses=['ControllerOutput','DeviceRepositoryProtocol'],
   inp=[['own (abstract API)',['@abstractmethod pair_device(discovery, credentials)','@abstractmethod unpair(device) / identify(device) / fetch(device)','@abstractmethod send_command(command, device, parameter)','@abstractproperty discoveries -> dict[UUID, Discovery]','start() / stop() / start_pairing_window(sec)']]],
   out=['dependencies.output: ControllerOutput   (→ Hub, via controller_did_*)'],
   deps=['dependencies.make_device_repository(): DeviceRepositoryProtocol','dependencies.zeroconf / ssdp / ble_discovery_service: *DiscoveryService','dependencies.documents_folder: Path','dependencies.hardware_interfaces: list[str]']),
 n('ctrlout','ControllerOutput','sdk','Protocol',pname='ControllerOutput',
   inp=[['own (protocol)',['controller_did_receive_discovery(controller, discovery)','controller_did_update_discovery / _lose_discovery(id)','controller_did_connect_device(id) / _lose_device(id)','controller_did_receive_events(controller, events)','controller_did_encounter_error(controller, message, still_running)','controller_did_emit_notification(controller, notification)']]]),
 n('dzc','ZeroconfDiscovery','sdk','class ZeroconfDiscoveryService',
   inp=[['own',['register(listener, services: set[str]) -> cancel','start() / stop() · async_zeroconf']]],
   out=['listener: ZeroconfDiscoveryListener   (zeroconf_did_discover / _update / _remove_service(ZeroconfDiscoveryInfo))']),
 n('dssdp','SSDPDiscovery','sdk','class SSDPDiscoveryService',
   inp=[['own',['register(listener, search_target, mcast, port) -> cancel','start() / stop() / perform_scan()']]],
   out=['listener: SSDPDiscoveryListener   (ssdp_did_discover / _update / _remove_service(SSDPDiscoveryInfo))']),
 n('dble','BLEDiscovery','sdk','class BLEDiscoveryService',
   inp=[['own',['register(listener, service_ids: set[UUID]) -> cancel','start() / stop() / perform_scan()']]],
   out=['listener: BLEDiscoveryListener   (ble_did_discover / _update / _remove_device(BLEDiscoveryInfo))']),
 n('devrepoproto','DeviceRepositoryProtocol','sdk','Protocol (runtime_checkable)',pname='DeviceRepositoryProtocol',
   inp=[['own (protocol)',['get_all(as_) / get(id, as_)','state(id) / get_parameter_state(id, parameter_id)','save(device, previous_id) / save_parameter_state(id, state)']]]),
 n('matter','MatterController','integrations','class : AbstractController','AbstractController',impl=['ZeroconfDiscoveryListener','BLEDiscoveryListener'],uses=['ControllerOutput','DeviceRepositoryProtocol'],
   inp=[['AbstractController (overrides)',['pair_device(discovery, credentials) / unpair / identify','fetch(device) / send_command(command, device, parameter)','discoveries -> dict[UUID, Discovery]']],
        ['ZeroconfDiscoveryListener · BLEDiscoveryListener',['zeroconf_did_discover_service(info) / _update / _remove','ble_did_discover_service(info) / _update / _remove']]],
   out=['dependencies.output: ControllerOutput   (→ RelayController)'],
   deps=['make_device_repository(): DeviceRepositoryProtocol','zeroconf / ble_discovery_service   (registers as listener)']),
 n('zigbee','ZigBeeController','integrations','class : AbstractController','AbstractController',uses=['ControllerOutput','DeviceRepositoryProtocol'],
   inp=[['AbstractController (overrides)',['pair_device / unpair / identify / fetch / send_command','discoveries -> dict[UUID, Discovery]   (via the radio)']]],
   out=['dependencies.output: ControllerOutput   (→ RelayController)'],
   deps=['make_device_repository(): DeviceRepositoryProtocol','hardware_interfaces: list[str]   (serial radio — DI)']),
 n('homekit','HomeKitController','integrations','class : AbstractController','AbstractController',impl=['ZeroconfDiscoveryListener','BLEDiscoveryListener'],uses=['ControllerOutput','DeviceRepositoryProtocol'],
   inp=[['AbstractController (overrides)',['pair_device(discovery, credentials) / unpair / identify','fetch(device) / send_command(command, device, parameter)','discoveries -> dict[UUID, Discovery]']],
        ['ZeroconfDiscoveryListener · BLEDiscoveryListener',['zeroconf_did_discover_service(info) / _update / _remove','ble_did_discover_service(info) / _update / _remove']]],
   out=['dependencies.output: ControllerOutput   (→ RelayController)'],
   deps=['make_device_repository(): DeviceRepositoryProtocol','zeroconf / ble_discovery_service   (registers as listener)']),
 n('hubprov','HubProvider','providers','class · nested Dependencies',
   inp=[['own',['setup_hub(hub_auth, hub_info, user_info, house_info)']]],
   deps=['dependencies.user / house / hub / credentials_repository']),
 n('roomman','RoomManager','providers','class',
   inp=[['own',['get(id) -> Room / create(RoomCreate) / patch(id, RoomPatch) / delete(id)']]],
   deps=['house_repository: HouseRepository','session: AsyncSession']),
 n('netprov','NetworkProvider','providers','class (+ NetworkProviderMock)',
   inp=[['own',['get_hotspots() -> list[Hotspot] / connect_wifi(ssid, pw)','is_connected() / reset_wifi() / apply_hostname(host)']]],
   deps=['rpi_networking   (OS network stack)']),
 n('cloudsvc','CloudService','cloud','class · Service · boundary','—',impl=['Service'],
   inp=[['Service',['start(): cloud/bridge WS client + auto-reconnect','stop()']],['own',['send_message(msg)']]],
   out=['websocket   (→ cloud, Settings().api_url)'],
   deps=['get_ws_manager(): WsMessageHandler']),
 n('wshandler','WsMessageHandler','cloud','class',uses=['DeviceCommandSender'],
   inp=[['own',['handle_message(msg: str) -> str | None','(device_command → delegate.send_command · bridge → local_request)']]],
   out=['delegate.send_command: DeviceCommandSender   (→ RelayController)'],
   deps=['local_request: LocalRequestFn   (→ utils.api.local_request)']),
 n('wssender','WsMessageSenderRelay','cloud','class','—',impl=['WsMessageSender'],
   inp=[['WsMessageSender',['send_message(msg)']],['own',['send_discovery / send_event / send_notification','send_device_connected / send_device_disconnected / send_integration_error']]],
   out=['connection_manager.broadcast: WsConnectionManager','cloud_service.send_message: WsMessageSender   (→ CloudService)']),
 n('wsconn','WsConnectionManager','cloud','class',
   inp=[['own',['connect(ws) / disconnect(ws)','send_message(ws, message) / broadcast(message)']]],
   out=['_connections: list[WebSocket]   (broadcast targets)']),
 n('gpio','GpioService','hardware','class : rpi_reactive_gpio.Scene','Scene',impl=['Service'],
   inp=[['Service',['start() / stop()  — front-panel buttons + status LEDs']]],
   out=['rpi_reactive_gpio (LedManager / ButtonClick)'],
   deps=['callbacks: is_initialized / ws_connected   (from Coordinator)']),
 n('hotspot','HotspotService','hardware','class (+ HotspotServiceMock)','—',impl=['Service'],
   inp=[['own',['hotspot_up() / hotspot_down()']],['Service',['start() / stop()']]],
   out=['rpi_networking.hotspot']),
 n('devrepo','DeviceRepository','repositories','class · shared (highest in-degree)','—',impl=['DeviceRepositoryProtocol'],
   inp=[['DeviceRepositoryProtocol',['get_all(as_) / get(id, as_) / state(id)','get_parameter_state(id, pid)','save(device, previous_id) / save_parameter_state(id, state)']],
        ['own',['delete(id) / mark_paired(id) / mark_unpaired(id)','update_parameter_visibility(pid, visibility)   (integration-scoped)']]],
   deps=['session: AsyncSession','models: Device · Parameter · ParameterState']),
 n('houserepo','HouseRepository','repositories','class',
   inp=[['own',['get() -> House / save(HouseInfo)']]],deps=['session: AsyncSession   → House (ORM)']),
 n('hubrepo','HubRepository','repositories','class',
   inp=[['own',['get() -> Hub / save(HubInfo) / patch(HubPatch)']]],deps=['session: AsyncSession   → Hub (ORM)']),
 n('userrepo','UserRepository','repositories','class',
   inp=[['own',['get(id) -> User / save(User)']]],deps=['session: AsyncSession   → User (ORM)']),
 n('credrepo','CredentialsRepository','repositories','class · file-backed',
   inp=[['own',['save_credentials(HubAuthItems) / save_tokens(TokensPair)']]],
   out=['on_new_tokens: Callable   (→ Coordinator.reconnect_cloud)'],
   deps=['Paths.data.tokens / keys (files) · mutates config globals']),
 n('models','models/ (ORM)','model','SQLAlchemy DeclarativeBase entities','DeclarativeBase',
   inp=[['own',['Device · Parameter · ParameterState (junction)','House · Room · Hub · User · ServiceOverride','columns · relationships() · cascades']]]),
 n('schemas','schemas/ (DTOs·SDK·DSL)','model','pydantic · TypedBaseModel','DiscriminatedBaseModel',uses=['SDK schemas'],
   inp=[['own',['re-exports SDK Device / Parameter / DeviceCommand / Discovery','automation DSL: _Condition (& | ~) · _Executable · Automation · Scene','transport envelopes: ws · http']]]),
 n('utils','utils/ auth·db·api·thread','utils','modules',
   inp=[['own',['create_async_session() -> AsyncSession / create_session()','RS256 JWT: BaseToken / User·Hub·DeviceToken / validator(type, role)','api.request() cloud client / local_request()','ServiceThread · coders · factory_reset']]]),
]
NODES={x['id']:x for x in N}
DOM={x['id']:x['domain'] for x in N}; LAB={x['id']:x['label'] for x in N}
EMPH={'coord','relay','devrepo'}
BOUNDARY={'relay','cloudsvc','absctrl','serversvc','autosvc'}   # devrepo removed — repositories have no single core-boundary
# names → node id (for clickable links in the sidebar)
NAME2ID={x['label']:x['id'] for x in N}
NAME2ID.update({'AbstractController':'absctrl','ControllerOutput':'ctrlout','DeviceRepositoryProtocol':'devrepoproto',
'DeviceRepository':'devrepo','RelayController':'relay','Coordinator':'coord','DeviceProvider':'devprov',
'AutomationService':'autosvc','EventBusImpl':'eventbus','MatterController':'matter','ZigBeeController':'zigbee',
'HomeKitController':'homekit','HubProvider':'hubprov','NetworkProvider':'netprov','RoomManager':'roomman',
'CloudService':'cloudsvc','WsMessageHandler':'wshandler','WsMessageSenderRelay':'wssender','WsConnectionManager':'wsconn',
'ServerService':'serversvc','ServiceManager':'svcmgr','HouseRepository':'houserepo','HubRepository':'hubrepo',
'UserRepository':'userrepo','CredentialsRepository':'credrepo','IgnoredDiscoveryRepository':'ignrepo',
'GpioService':'gpio','HotspotService':'hotspot','MinuteTickerService':'ticker','schemas':'schemas','models':'models',
'DeviceParameterChecker':'ckdev','RoomUnitChecker':'ckroom','CronChecker':'ckcron','TimeIntervalChecker':'cktime',
'DeviceActionHandler':'hdev','FunctionActionHandler':'hfunc','TextActionHandler':'htext',
'ZeroconfDiscovery':'dzc','SSDPDiscovery':'dssdp','BLEDiscovery':'dble'})

SECT={'core':(0,0),'server':(2,1),'automation':(90,1),'devctl':(180,1),'cloud':(-58,1),'hardware':(258,1),
'providers':(26,2),'repositories':(-20,2),'integrations':(157,2),'sdk':(203,2),'model':(0,3),'utils':(-40,3)}
RING={0:0,1:335,2:575,3:790}
E=[
('coord','serversvc','own'),('coord','autosvc','own'),('coord','relay','own'),('coord','cloudsvc','own'),
('coord','gpio','own'),('coord','hotspot','own'),('coord','ticker','own'),('coord','svcmgr','own'),
('coord','dzc','own'),('coord','dssdp','own'),('coord','dble','own'),('coord','netprov','own'),('coord','wssender','own'),('coord','config','own'),
('serversvc','endpoints','use'),('serversvc','deps','use'),('endpoints','wsend','use'),('endpoints','wsdocs','use'),
('endpoints','devprov','use'),('endpoints','hubprov','use'),('endpoints','roomman','use'),('endpoints','automan','use'),
('endpoints','houserepo','use'),('endpoints','hubrepo','use'),('endpoints','devrepo','use'),
('deps','devprov','use'),('deps','hubprov','use'),('deps','netprov','use'),('deps','roomman','use'),
('wsend','wshandler','use'),('wsend','wsconn','use'),
('autosvc','eventbus','use'),('autosvc','automan','use'),
('autosvc','ckdev','use'),('autosvc','ckroom','use'),('autosvc','ckcron','use'),('autosvc','cktime','use'),
('autosvc','hdev','use'),('autosvc','hfunc','use'),('autosvc','htext','use'),
('ticker','eventbus','use'),('relay','eventbus','use'),('eventbus','autosvc','obs'),
('hdev','relay','cmd'),('ckdev','devrepo','repo'),('ckroom','devrepo','repo'),
('devprov','relay','use'),('devprov','devrepo','repo'),
('hubprov','houserepo','use'),('hubprov','hubrepo','use'),('hubprov','userrepo','use'),('hubprov','credrepo','use'),
('roomman','houserepo','use'),('gpio','netprov','use'),('hotspot','netprov','use'),
('relay','ignrepo','repo'),('relay','devrepo','repo'),('relay','matter','use'),('relay','zigbee','use'),('relay','homekit','use'),
('relay','coord','sdk'),('matter','absctrl','impl'),('zigbee','absctrl','impl'),('homekit','absctrl','impl'),
('absctrl','ctrlout','sdk'),('absctrl','dzc','use'),('absctrl','dssdp','use'),('absctrl','dble','use'),('absctrl','devrepoproto','repo'),
('relay','ctrlout','impl'),('devrepo','devrepoproto','impl'),
('dzc','matter','dot'),('dble','matter','dot'),('dzc','homekit','dot'),('dble','homekit','dot'),
('cloudsvc','wshandler','use'),('wshandler','relay','cmd'),('wssender','wsconn','use'),('wssender','cloudsvc','use'),
('devrepo','models','pers'),('houserepo','models','pers'),('hubrepo','models','pers'),('userrepo','models','pers'),
('relay','schemas','pers'),('automan','schemas','pers'),('endpoints','schemas','pers'),
('devrepo','utils','dot'),('deps','utils','dot'),('cloudsvc','utils','dot'),
]
ECOL={'own':'#b6bdc8','use':'#8b95a4','cmd':'#0d8079','repo':'#c07d22','impl':'#8a6fbf','sdk':'#5b63c9','pers':'#a99263','obs':'#3fae86','dot':'#b6bdc8'}
EDASH={'impl','obs'}; EDOT={'dot'}
EDGES=[{'src':s,'dst':d,'type':t} for (s,d,t) in E]

CW=6.9; PADX=13; NH=25; RG=8; CG=16
cx,cy=790,690
# per-domain columns, ordered INNER (main actor, nearest core) -> OUTER; same role shares a column
COLS={
'core':[['coord'],['svcmgr'],['main','config']],
'server':[['serversvc'],['deps'],['endpoints','wsend','wsdocs']],
'automation':[['autosvc','eventbus','ticker'],['ckdev','ckroom','ckcron','cktime'],['hdev','hfunc','htext','automan']],
'devctl':[['relay','ignrepo']],
'sdk':[['absctrl'],['ctrlout','devrepoproto'],['dzc','dssdp','dble']],
'integrations':[['matter','zigbee','homekit']],
'providers':[['devprov','hubprov'],['roomman','netprov']],
'cloud':[['cloudsvc'],['wshandler','wssender','wsconn']],
'hardware':[['gpio','hotspot']],
'repositories':[['devrepo','houserepo','hubrepo'],['userrepo','credrepo']],
'model':[['schemas','models']],
'utils':[['utils']],
}
RADJ={'automation':95,'server':115,'cloud':70,'repositories':30,'providers':20,'hardware':110,'model':100}   # push these out to clear neighbours (devctl/sdk/integrations use ANCHOR)
def NW(nid): return len(LAB[nid])*CW+2*PADX
def layout_domain(dom,ax,ay,ux,uy):
    cols=[c[:] for c in COLS[dom]]; out={}
    if abs(ux)>=abs(uy):                      # horizontal domain: columns L->R
        order=cols if ux>=0 else cols[::-1]   # left-of-core: reverse so inner column faces core
        colw=[max(NW(n) for n in c) for c in order]; totalw=sum(colw)+CG*(len(order)-1); x=ax-totalw/2
        for i,c in enumerate(order):
            colh=len(c)*NH+RG*(len(c)-1); y=ay-colh/2
            for j,nid in enumerate(c): out[nid]=(x+(colw[i]-NW(nid))/2,y+j*(NH+RG),NW(nid),NH)
            x+=colw[i]+CG
    else:                                     # vertical domain: columns become rows, inner nearest core
        order=cols[::-1] if uy<0 else cols
        totalh=len(order)*NH+RG*(len(order)-1); y=ay-totalh/2
        for c in order:
            roww=sum(NW(n) for n in c)+CG*(len(c)-1); x=ax-roww/2
            for nid in c: out[nid]=(x,y,NW(nid),NH); x+=NW(nid)+CG
            y+=NH+RG
    return out
ANCHOR={'sdk':(285,470),'integrations':(250,620),'devctl':(300,730)}   # device-control sub-clusters, SDK on top
SUPER={'devctl':['devctl','integrations','sdk']}                        # device control wraps integrations + SDK
rects={}; hulls=[]
for dom,(ang,ring) in SECT.items():
    if dom in ANCHOR: ax,ay=ANCHOR[dom]
    else: R=RING[ring]+RADJ.get(dom,0); ax=cx+R*math.cos(math.radians(ang)); ay=cy-R*math.sin(math.radians(ang))
    r=layout_domain(dom,ax,ay,ax-cx,ay-cy); rects.update(r)
    xs=[v[0] for v in r.values()]; ys=[v[1] for v in r.values()]; xe=[v[0]+v[2] for v in r.values()]; ye=[v[1]+v[3] for v in r.values()]
    hulls.append((dom,min(xs)-14,min(ys)-24,max(xe)-min(xs)+28,max(ye)-min(ys)+38))
superhulls=[]   # bigger box around a set of sub-domains (extra top pad for its own label)
for sup,members in SUPER.items():
    ns=[nid for nid in rects if DOM[nid] in members]
    sx=[rects[n][0] for n in ns]; sy=[rects[n][1] for n in ns]; sxe=[rects[n][0]+rects[n][2] for n in ns]; sye=[rects[n][1]+rects[n][3] for n in ns]
    superhulls.append((sup,min(sx)-22,min(sy)-40,max(sxe)-min(sx)+44,max(sye)-min(sy)+62))
def esc(s): return html.escape(str(s),quote=True)
allh=hulls+superhulls
xs=[r[0] for r in rects.values()]+[h[1] for h in allh]; ys=[r[1] for r in rects.values()]+[h[2] for h in allh]
xe=[r[0]+r[2] for r in rects.values()]+[h[1]+h[3] for h in allh]; ye=[r[1]+r[3] for r in rects.values()]+[h[2]+h[4] for h in allh]
minx,miny=min(xs)-20,min(ys)-20; W,H=max(xe)+20-minx,max(ye)+20-miny
def border(x0,y0,w,h,tx,ty):
    dcx,dcy=x0+w/2,y0+h/2; dx,dy=tx-dcx,ty-dcy
    if dx==0 and dy==0: return dcx,dcy
    s=min(((w/2)/abs(dx)) if dx else 9e9,((h/2)/abs(dy)) if dy else 9e9); return dcx+dx*s,dcy+dy*s
svg=[f'<svg id="wire" viewBox="{minx:.0f} {miny:.0f} {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace,Menlo,monospace">']
def mk(c,i=''): return f'<marker id="m{c.strip("#")}{i}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker>'
svg.append('<defs>'+''.join(mk(c) for c in set(ECOL.values()))+mk('#2f81f7','IN')+mk('#e08a2b','OUT')+'</defs>')
for sup,x,y,w,h in superhulls:   # super-domain box (behind), e.g. device control wrapping integrations + SDK
    svg.append(f'<g class="hull super" data-dom="{sup}"><rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="16" fill="{FILL[sup]}" fill-opacity="0.07" stroke="{BORD[sup]}" stroke-width="1.5" stroke-dasharray="2 5"/><text class="hulllbl" data-dom="{sup}" x="{x+11:.0f}" y="{y+17:.0f}" font-size="11.5" font-weight="700" fill="{BORD[sup]}">{esc(LABEL[sup])} ⤢</text></g>')
for dom,x,y,w,h in hulls:
    if dom=='devctl': continue   # its nodes live directly inside the device-control super-box
    svg.append(f'<g class="hull" data-dom="{dom}"><rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="12" fill="{FILL[dom]}" fill-opacity="0.14" stroke="{BORD[dom]}" stroke-width="1.1" stroke-dasharray="5 4"/><text class="hulllbl" data-dom="{dom}" x="{x+8:.0f}" y="{y+15:.0f}" font-size="11" font-weight="700" fill="{BORD[dom]}">{esc(LABEL[dom])} ⤢</text></g>')
svg.append('<g id="edges">')
for e in EDGES:
    s,d,t=e['src'],e['dst'],e['type']
    if s not in rects or d not in rects: continue
    sx,sy,sw,sh=rects[s]; dx0,dy0,dw,dh=rects[d]
    x1,y1=border(sx,sy,sw,sh,dx0+dw/2,dy0+dh/2); x2,y2=border(dx0,dy0,dw,dh,sx+sw/2,sy+sh/2)
    c=ECOL[t]; mid=f'url(#m{c.strip("#")})'
    da=' stroke-dasharray="5 4"' if t in EDASH else (' stroke-dasharray="1.5 3.5"' if t in EDOT else '')
    wdt=1.5 if t in('repo','cmd','sdk') else 1.0
    mx,my=(x1+x2)/2,(y1+y2)/2; nx,ny=-(y2-y1),(x2-x1); ln=math.hypot(nx,ny) or 1; bow=min(26,ln*0.05)
    svg.append(f'<path class="edge" data-s="{s}" data-d="{d}" data-om="{mid}" d="M{x1:.0f} {y1:.0f} Q{mx+nx/ln*bow:.0f} {my+ny/ln*bow:.0f} {x2:.0f} {y2:.0f}" fill="none" stroke="{c}" stroke-width="{wdt}"{da} stroke-opacity="0.8" marker-end="{mid}"/>')
svg.append('</g><g id="nodes">')
for nid,(x,y,w,h) in rects.items():
    dom=DOM[nid]; emph=nid in EMPH; bnd=nid in BOUNDARY
    st='#3b4658' if nid=='coord' else '#8a5a12' if nid in('relay','devrepo') else BORD[dom]
    sw=2.4 if emph else (1.9 if bnd else 1.1)
    svg.append(f'<g class="node" data-id="{nid}" tabindex="0"><rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="7" fill="{FILL[dom]}" stroke="{st}" stroke-width="{sw}"/>')
    if bnd: svg.append(f'<circle cx="{x+7:.0f}" cy="{y+7:.0f}" r="2.6" fill="{st}"/>')
    svg.append(f'<text x="{x+w/2:.0f}" y="{y+h/2+4:.0f}" font-size="12" text-anchor="middle" fill="#182231" font-weight="{700 if emph else 500}">{esc(LAB[nid])}</text></g>')
svg.append('</g></svg>')
SVG='\n'.join(svg)
DATA=json.dumps({'nodes':NODES,'dom':LABEL,'bord':BORD,'n2i':NAME2ID,'super':SUPER})
CSS='''
 :root{--bg:#f4f6f8;--surface:#ffffff;--surface-2:#eef1f5;--ink:#151a22;--ink-2:#495162;--ink-3:#6c7686;--line:#dbe1ea;--accent:#0d7a83;--accent-ink:#0a5a61;--in:#2f81f7;--out:#e08a2b;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
 @media (prefers-color-scheme:dark){:root{--bg:#0b0e14;--surface:#121722;--surface-2:#1a202b;--ink:#e8ecf3;--ink-2:#9aa5b6;--ink-3:#727d8d;--line:#232d3c;--accent:#45c8c0;--accent-ink:#82ddd7;--in:#5aa1ff;--out:#f0a53c;}}
 :root[data-theme="dark"]{--bg:#0b0e14;--surface:#121722;--surface-2:#1a202b;--ink:#e8ecf3;--ink-2:#9aa5b6;--ink-3:#727d8d;--line:#232d3c;--accent:#45c8c0;--accent-ink:#82ddd7;--in:#5aa1ff;--out:#f0a53c;}
 :root[data-theme="light"]{--bg:#f4f6f8;--surface:#ffffff;--surface-2:#eef1f5;--ink:#151a22;--ink-2:#495162;--ink-3:#6c7686;--line:#dbe1ea;--accent:#0d7a83;--accent-ink:#0a5a61;--in:#2f81f7;--out:#e08a2b;}
 *{box-sizing:border-box;} body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.55;-webkit-font-smoothing:antialiased;}
 .wrap{max-width:1740px;margin:0 auto;padding:22px 22px 70px;}
 .kicker{font-family:var(--mono);font-size:12px;letter-spacing:.15em;text-transform:uppercase;color:var(--accent-ink);display:inline-flex;align-items:center;gap:8px;margin:0 0 8px;}
 .kicker .dot{width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 3px color-mix(in oklab,var(--accent) 25%,transparent);}
 h1{font-size:clamp(23px,3vw,33px);margin:0 0 6px;letter-spacing:-.02em;font-weight:770;} h1 .thin{color:var(--ink-2);font-weight:500;}
 .lede{font-size:15px;color:var(--ink-2);max-width:102ch;margin:0 0 14px;} .lede code,.lede b{font-family:var(--mono);font-size:.9em;} .lede code{background:var(--surface-2);border:1px solid var(--line);border-radius:5px;padding:.5px 5px;}
 .legend{display:flex;flex-wrap:wrap;gap:14px 26px;margin:0 0 12px;padding:12px 14px;background:var(--surface-2);border:1px solid var(--line);border-radius:12px;}
 .lgroup{display:flex;flex-direction:column;gap:6px;} .lgroup .h{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);}
 .lrow{display:flex;flex-wrap:wrap;gap:5px 12px;} .li{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px;color:var(--ink-2);}
 .sw{width:12px;height:12px;border-radius:3px;flex:none;border:1px solid rgba(120,130,145,.55);} .ln{width:20px;height:0;border-top:2.4px solid var(--x);flex:none;} .ln.dash{border-top-style:dashed;}
 .app{display:flex;gap:16px;align-items:flex-start;}
 .wire-wrap{flex:1;min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px;overflow:auto;}
 svg#wire{width:100%;min-width:1120px;height:auto;display:block;}
 .hint{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);margin:8px 2px 0;}
 svg#wire.focus .node:not(.sel):not(.nbr) rect{opacity:.18;} svg#wire.focus .node:not(.sel):not(.nbr) circle{opacity:.2;} svg#wire.focus .node:not(.sel):not(.nbr) text{opacity:.72;}
 svg#wire.focus .hull{opacity:.4;}
 svg#wire.focus .edge{opacity:.05;}
 svg#wire.focus .edge.eIn{opacity:1;stroke:var(--in)!important;stroke-width:2.2!important;}
 svg#wire.focus .edge.eOut{opacity:1;stroke:var(--out)!important;stroke-width:2.2!important;}
 .node{cursor:pointer;} .node.sel rect{stroke-width:3.2!important;}
 .side{width:392px;flex:none;background:var(--surface);border:1px solid var(--line);border-radius:12px;position:sticky;top:14px;max-height:calc(100vh - 28px);overflow:auto;}
 .side h3{margin:0;padding:14px 40px 4px 16px;font-size:15px;}
 .side .dm{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;padding:0 16px;}
 .side .kind{font-family:var(--mono);font-size:12px;color:var(--ink-2);padding:6px 16px 0;}
 .side .rel{font-family:var(--mono);font-size:11.5px;color:var(--ink-2);padding:2px 16px;} .side .rel b{color:var(--ink);}
 .side .sec{margin-top:10px;padding:9px 16px;border-top:1px solid var(--line);}
 .side .sec h4{margin:0 0 7px;font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;}
 h4.hin{color:var(--in);} h4.hout{color:var(--out);} h4.hdep{color:var(--ink-3);}
 .side .grp{font-family:var(--mono);font-size:10px;color:var(--ink-3);margin:9px 0 3px;letter-spacing:.03em;}
 .side .grp .g{color:var(--in);}
 .side .m{font-family:var(--mono);font-size:11px;color:var(--ink-2);white-space:pre-wrap;padding:2.5px 0;}
 .side .m.in{border-left:2px solid var(--in);padding-left:9px;margin:2px 0;} .side .m.out{border-left:2px solid var(--out);padding-left:9px;margin:2px 0;} .side .m.dep{border-left:2px solid var(--ink-3);padding-left:9px;margin:2px 0;}
 .side .close{position:absolute;top:12px;right:12px;cursor:pointer;color:var(--ink-3);font-family:var(--mono);font-size:15px;background:none;border:none;}
 .side .empty{padding:22px 16px;color:var(--ink-3);font-size:13px;}
 .lnk{color:var(--accent-ink);cursor:pointer;border-bottom:1px dotted color-mix(in oklab,var(--accent-ink) 55%,transparent);}
 .lnk:hover{color:var(--accent);}
 .hulllbl{cursor:pointer;} .hulllbl:hover{text-decoration:underline;}
 .toolbar{display:flex;gap:10px;align-items:center;margin:0 0 8px;}
 .toolbar input{font-family:var(--mono);font-size:13px;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 11px;width:300px;}
 .toolbar input:focus{outline:2px solid color-mix(in oklab,var(--accent) 45%,transparent);border-color:var(--accent);}
 .toolbar .cnt{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);}
 .toolbar .banner{font-family:var(--mono);font-size:11.5px;color:var(--ink);background:var(--surface-2);border:1px solid var(--line);border-radius:999px;padding:4px 11px;display:none;align-items:center;gap:8px;}
 .toolbar .banner.on{display:inline-flex;} .toolbar .banner b{color:var(--accent-ink);} .toolbar .banner .x{cursor:pointer;color:var(--ink-3);}
 /* search dim */
 svg#wire.searching .node:not(.hit) rect{opacity:.13;} svg#wire.searching .node:not(.hit) text{opacity:.5;} svg#wire.searching .node:not(.hit) circle{opacity:.13;}
 svg#wire.searching .node.hit rect{stroke-width:3!important;} svg#wire.searching .edge{opacity:.08;}
 /* isolate domain */
 svg#wire.iso .node.dout rect{opacity:.12;} svg#wire.iso .node.dout text{opacity:.4;} svg#wire.iso .node.dout circle{opacity:.12;}
 svg#wire.iso .hull.hout{opacity:.28;} svg#wire.iso .edge.eout{opacity:.04;}
 .ideas{margin-top:16px;border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:0 16px;max-width:1100px;}
 .ideas summary{cursor:pointer;padding:13px 0;font-family:var(--mono);font-size:12.5px;color:var(--ink);font-weight:600;letter-spacing:.02em;}
 .ideas summary::marker{color:var(--accent);}
 .ideas ul{margin:0 0 14px;padding-left:20px;} .ideas li{font-size:13px;color:var(--ink-2);margin:5px 0;} .ideas li b{color:var(--ink);}
 .ideas .done{color:var(--ink-3);} .ideas .done b{color:var(--ink-3);}
 @media(max-width:980px){.app{flex-direction:column;} .side{width:100%;position:static;max-height:none;} .toolbar input{width:100%;}}
'''
domchips=''.join(f'<span class="li"><span class="sw" style="background:{FILL[k]}"></span>{esc(LABEL[k])}</span>' for k in ['core','server','automation','devctl','sdk','integrations','providers','cloud','hardware','repositories','model'])
JS=r'''
const D=__DATA__;
const svg=document.getElementById('wire'),side=document.getElementById('side'),body=document.getElementById('sidebody');
const NAMES=Object.keys(D.n2i).sort((a,b)=>b.length-a.length);
const RE=new RegExp('('+NAMES.map(s=>s.replace(/[.*+?^${}()|[\]\\/]/g,'\\$&')).join('|')+')','g');
function esc(s){return (s+'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function L(t){return esc(t).replace(RE,m=>'<span class="lnk" data-go="'+D.n2i[m]+'">'+m+'</span>');}
const EMPTY='<div class="empty">Click any entity in the map to inspect it — its kind, what it implements / consumes, the methods callers invoke (grouped by where they were declared), its output ports and injected dependencies.</div>';
function setEmpty(){body.innerHTML=EMPTY;}
const searchEl=document.getElementById('search'),cntEl=document.getElementById('cnt'),bannerEl=document.getElementById('banner');
function clearSearch(){svg.classList.remove('searching');svg.querySelectorAll('.node.hit').forEach(n=>n.classList.remove('hit'));cntEl.textContent='';}
function clearIso(){svg.classList.remove('iso');svg.querySelectorAll('.dout,.hout,.eout').forEach(e=>e.classList.remove('dout','hout','eout'));bannerEl.classList.remove('on');bannerEl.innerHTML='';}
function reset(){svg.classList.remove('focus');svg.querySelectorAll('.node').forEach(n=>n.classList.remove('sel','nbr'));
 svg.querySelectorAll('.edge').forEach(p=>{p.classList.remove('eIn','eOut');p.setAttribute('marker-end',p.dataset.om);});clearIso();clearSearch();setEmpty();history.replaceState(null,'','#');}
function isolate(dom){reset();svg.classList.add('iso');const doms=D.super[dom]||[dom];
 svg.querySelectorAll('.node').forEach(n=>{const nd=D.nodes[n.dataset.id];if(nd&&!doms.includes(nd.domain))n.classList.add('dout');});
 svg.querySelectorAll('.hull').forEach(h=>{if(!doms.includes(h.dataset.dom))h.classList.add('hout');});
 svg.querySelectorAll('.edge').forEach(p=>{const s=D.nodes[p.dataset.s],d=D.nodes[p.dataset.d];if(!((s&&doms.includes(s.domain))||(d&&doms.includes(d.domain))))p.classList.add('eout');});
 bannerEl.classList.add('on');bannerEl.innerHTML='isolated: <b>'+esc(D.dom[dom])+'</b> <span class="x">✕</span>';}
function runSearch(q){q=q.trim().toLowerCase();if(!q){clearSearch();return [];}let hits=[];
 svg.querySelectorAll('.node').forEach(n=>{const nd=D.nodes[n.dataset.id];const m=nd&&(nd.label.toLowerCase().includes(q)||n.dataset.id.includes(q));n.classList.toggle('hit',!!m);if(m)hits.push(n.dataset.id);});
 svg.classList.add('searching');cntEl.textContent=hits.length+' match'+(hits.length===1?'':'es');return hits;}
function focus(id){const n=D.nodes[id];if(!n)return;clearIso();clearSearch();svg.classList.add('focus');
 svg.querySelectorAll('.node').forEach(x=>x.classList.remove('sel','nbr'));
 svg.querySelector('.node[data-id="'+id+'"]').classList.add('sel');
 const nbrs=new Set();
 svg.querySelectorAll('.edge').forEach(p=>{p.classList.remove('eIn','eOut');
  if(p.dataset.d===id){p.classList.add('eIn');p.setAttribute('marker-end','url(#m2f81f7IN)');nbrs.add(p.dataset.s);}
  else if(p.dataset.s===id){p.classList.add('eOut');p.setAttribute('marker-end','url(#me08a2bOUT)');nbrs.add(p.dataset.d);}
  else p.setAttribute('marker-end',p.dataset.om);});
 nbrs.forEach(x=>{const el=svg.querySelector('.node[data-id="'+x+'"]');if(el)el.classList.add('nbr');});
 let implementers=[]; if(n.pname) implementers=Object.values(D.nodes).filter(m=>(m.impl||[]).includes(n.pname)).map(m=>m.label);
 const isProto=n.kind.indexOf('Protocol')>=0;
 let h='<h3>'+esc(n.label)+'</h3><div class="dm" style="color:'+D.bord[n.domain]+'">'+esc(D.dom[n.domain])+'</div><div class="kind">'+L(n.kind)+'</div>';
 if(n.base&&n.base!=='—')h+='<div class="rel">subclass of <b>'+L(n.base)+'</b></div>';
 if(n.impl&&n.impl.length)h+='<div class="rel">implements <b>'+n.impl.map(L).join(', ')+'</b></div>';
 if(n.uses&&n.uses.length)h+='<div class="rel">consumes <b>'+n.uses.map(L).join(', ')+'</b></div>';
 if(implementers.length)h+='<div class="rel">implemented by <b>'+implementers.map(L).join(', ')+'</b></div>';
 h+='<div class="sec"><h4 class="hin">Inputs ◂ '+(isProto?'protocol methods callers invoke':'methods / props called on this')+'</h4>';
 if(n.inp&&n.inp.length){n.inp.forEach(g=>{const src=g[0];const lab=src==='own'||src.indexOf('own')===0?'<span style="color:var(--ink-3)">'+esc(src)+'</span>':'from '+L(src);
   h+='<div class="grp">◂ '+lab+'</div>'+g[1].map(s=>'<div class="m in">'+L(s)+'</div>').join('');});}
 else h+='<div class="m" style="color:var(--ink-3)">— none —</div>';
 h+='</div><div class="sec"><h4 class="hout">Outputs ▸ delegates it calls to emit results (prop: Type)</h4>';
 h+=(n.out&&n.out.length)?n.out.map(s=>'<div class="m out">'+L(s)+'</div>').join(''):'<div class="m" style="color:var(--ink-3)">— none (returns values / pure sink) —</div>';
 h+='</div><div class="sec"><h4 class="hdep">Injected dependencies ▹ collaborators it is given</h4>';
 h+=(n.deps&&n.deps.length)?n.deps.map(s=>'<div class="m dep">'+L(s)+'</div>').join(''):'<div class="m" style="color:var(--ink-3)">— none —</div>';
 h+='</div>';
 body.innerHTML=h;if(location.hash.slice(1)!==id)history.replaceState(null,'','#'+id);}
svg.querySelectorAll('.node').forEach(nd=>{nd.addEventListener('click',ev=>{ev.stopPropagation();focus(nd.dataset.id);});
 nd.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();focus(nd.dataset.id);}});});
svg.addEventListener('click',reset);
side.addEventListener('click',ev=>{const l=ev.target.closest('.lnk');if(l&&D.nodes[l.dataset.go])focus(l.dataset.go);});
document.getElementById('close').addEventListener('click',reset);
svg.querySelectorAll('.hulllbl').forEach(t=>t.addEventListener('click',ev=>{ev.stopPropagation();isolate(t.dataset.dom);}));
bannerEl.addEventListener('click',ev=>{if(ev.target.classList.contains('x'))reset();});
searchEl.addEventListener('input',()=>{clearIso();runSearch(searchEl.value);});
searchEl.addEventListener('keydown',e=>{if(e.key==='Enter'){const h=runSearch(searchEl.value);if(h.length){searchEl.blur();focus(h[0]);}}else if(e.key==='Escape'){searchEl.value='';clearSearch();searchEl.blur();}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){reset();}else if(e.key==='/'&&document.activeElement!==searchEl){e.preventDefault();searchEl.focus();}});
setEmpty();
if(location.hash.slice(1)&&D.nodes[location.hash.slice(1)])focus(location.hash.slice(1));
'''.replace('__DATA__',DATA)
PAGE=f'''<meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">\n<title>MajorDom Hub — Interactive Module Map</title>
<style>{CSS}</style>
<div class="wrap">
 <div class="legend">
  <div class="lgroup"><span class="h">Relation</span><div class="lrow">
   <span class="li"><span class="ln" style="--x:#b6bdc8"></span>owns</span><span class="li"><span class="ln" style="--x:#8b95a4"></span>uses</span>
   <span class="li"><span class="ln" style="--x:#0d8079"></span>send_command</span><span class="li"><span class="ln" style="--x:#c07d22"></span>shared repo</span>
   <span class="li"><span class="ln dash" style="--x:#8a6fbf"></span>subclass/implements</span><span class="li"><span class="ln" style="--x:#5b63c9"></span>SDK callback</span>
   <span class="li"><span class="ln" style="--x:#a99263"></span>persists&#8594;model</span>
   <span class="li"><span class="ln" style="--x:#2f81f7"></span><b>input (focus)</b></span><span class="li"><span class="ln" style="--x:#e08a2b"></span><b>output (focus)</b></span>
  </div></div>
  <div class="lgroup"><span class="h">Domain</span><div class="lrow">{domchips}</div></div>
 </div>
 <div class="toolbar">
  <input id="search" type="text" placeholder="Search entities…  (press /)" autocomplete="off" spellcheck="false">
  <span class="cnt" id="cnt"></span>
  <span class="banner" id="banner"></span>
 </div>
 <div class="app">
  <div class="wire-wrap">{SVG}
   <p class="hint">● = domain boundary · click a node (or a link in the panel) to focus · click a domain's <b>⤢</b> label to isolate it · press <b>/</b> to search · click empty space / Esc to reset</p>
  </div>
  <aside class="side" id="side"><button class="close" id="close">✕</button><div id="sidebody"></div></aside>
 </div>
 <details class="ideas">
  <summary>💡 Ideas &amp; roadmap — parked for later</summary>
  <ul>
   <li><b>Transitive focus</b> — shift-click to light the full downstream / upstream chain ("what breaks if I change this").</li>
   <li><b>Relation-type filters</b> — turn the legend chips into toggles (show only <i>implements</i>, hide <i>owns</i>).</li>
   <li><b>Split endpoints</b> — optionally break <code>endpoints /api/v1</code> into its 7 resource routers.</li>
   <li><b>AST-generated metadata</b> — derive the node/edge dicts from an AST pass over the repo so the map can't drift from code.</li>
   <li><b>Coupling heatmap</b> — colour domains by cross-domain edge count; surface the most-coupled seams.</li>
   <li><b>Export focused subgraph</b> — copy a node's neighbourhood as text or an image.</li>
   <li class="done"><b>Done:</b> click-to-focus &amp; mute · input/output colour split · inputs grouped by declarer · outputs vs injected deps · clickable cross-links · always-on sidebar · deep-linking · role-column layout · search · isolate-domain · split checkers/handlers/discovery.</li>
  </ul>
 </details>
</div>
<script>{JS}</script>'''
_HERE=__import__("pathlib").Path(__file__).resolve().parent
_OUT=_HERE.parent/"docs"/"hub"
(_OUT/"module-map.html").write_text(PAGE)
print("ok nodes",len(rects),"edges",len(EDGES),"viewBox %.0fx%.0f"%(W,H))
