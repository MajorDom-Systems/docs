"""MajorDom — interactive map of every peripheral the SDK runtime runs, drawn like the Hub's module map.

Run:  python tools/peripherals_map.py
Emits: docs/hub/peripherals-map.html

Edges point from a provider to the peripheral whose need it serves. The integrations are examples of consumers.
"""
from module_map import render

FILL={'runtime':'#e3e7ee','hardware':'#eae7dc','drivers':'#e9e3f8','services':'#dce9f7','providers':'#dff0f0',
'ble':'#e6efd9','integrations':'#f0e0e0'}
BORD={'runtime':'#8a93a2','hardware':'#a99e86','drivers':'#8a6fbf','services':'#5aa9e0','providers':'#3a9a9a',
'ble':'#7fa05a','integrations':'#c25f5f'}
LABEL={'runtime':'runtime','hardware':'hardware & host','drivers':'USB drivers','services':'services (Docker)',
'providers':'in-process capabilities','ble':'Bluetooth radios','integrations':'integrations (examples)'}


def n(id,label,domain,kind,needs=None,provides=None,by=None):
    return {'id':id,'label':label,'domain':domain,'kind':kind,'base':'—','impl':[],'uses':[],
            'inp':[['needs',needs]] if needs else [],'out':provides or [],'deps':by or [],'pname':None}


N=[
 n('runtime','Runtime','runtime','majordom_integration_sdk.runtime · binds every need to a provider',
   provides=['runs every peripheral below, in the order it is given','binds each need to the first provider that can serve it']),
 n('pinned','Pinned','hardware','endpoints run elsewhere, preferred over anything found',
   provides=['any family: e.g. zigbee/ezsp at socket://…, matter/matter-server at ws://…'],by=['Runtime']),
 n('board','FixedPeripherals','hardware','radios soldered on the board (the Hub\'s board profile: FixedRadio)',
   provides=['a Radio per soldered radio'],by=['Runtime']),
 n('usb','UsbScanner','hardware','USB sticks as they are plugged in, recognised by the USB drivers',
   needs=['usb-driver (every driver)'],provides=['a Radio per stick'],by=['Runtime']),
 n('radio','Radio','hardware','one stick or soldered radio, per firmware',
   provides=['zigbee/ezsp · thread/spinel · multipan/silabs-cpc · zwave/serial-api','ble/silabs-cpc-hci (multi-PAN firmware with Bluetooth)'],
   by=['UsbScanner','FixedPeripherals']),
 n('btadapters','BluetoothAdapters','hardware','the host\'s Bluetooth adapters',
   provides=['ble/bluez per adapter (hci0, hci1, …)'],by=['Runtime']),
 n('host','HostNetwork','hardware','the host\'s network',provides=['ip (shared)'],by=['Runtime']),
 n('silabs','Silabs','drivers','UsbDriver: Silicon Labs sticks',
   provides=['firmwares: zigbee-ncp · thread-rcp · multipan-rcp'],by=['Runtime (default_usb_drivers)']),
 n('zwavedrv','ZWave','drivers','UsbDriver: Z-Wave sticks',provides=['firmware: serial-api'],by=['Runtime (default_usb_drivers)']),
 n('zigpydrv','ZigpyDriver','drivers','UsbDriver an integration brings: sticks only zigpy tells apart',
   provides=['zigbee/znp · deconz · xbee · zigate · …'],by=['ZigBeeController\'s peripherals()']),
 n('compose','Compose','services','runs the services: docker compose project "majordom"',
   provides=['container/compose: what every Service needs'],by=['Runtime']),
 n('multipan','silabs-multiprotocol','services','SDK Service: one multi-PAN stick as Zigbee and Thread',
   needs=['multipan/silabs-cpc','container/compose'],provides=['zigbee/ezsp at socket://127.0.0.1:{ports.ezsp}','thread/otbr-rest (shared)'],by=['Runtime']),
 n('otbr','otbr','services','SDK Service: OpenThread Border Router on a Thread RCP',
   needs=['thread/spinel','container/compose'],provides=['thread/otbr-rest (shared)'],by=['Runtime']),
 n('mjs','matterjs-server','services','Service an integration brings',
   needs=['ip','thread/otbr-rest (optional)','ble/bluez (optional)','container/compose'],provides=['matter/matter-server'],by=['MatterController\'s peripherals()']),
 n('zjs','zwave-js-server','services','Service an integration brings',
   needs=['zwave/serial-api','container/compose'],provides=['zwave/zwave-js-ws'],by=['ZwaveController\'s peripherals()']),
 n('router','BLERouter','providers','ble/router · BLE_ROUTER: discovery, connections, leases',
   needs=['ble/bluez · ble/silabs-cpc-hci · ble/esphome-proxy (every one, optional)'],provides=['ble/router (shared)'],by=['Runtime']),
 n('zeroconf','Zeroconf','providers','mdns/zeroconf · ZEROCONF: DNS-SD over mDNS',provides=['mdns/zeroconf (shared)'],by=['Runtime']),
 n('ssdp','SSDP','providers','upnp/ssdp · UPNP_SSDP',provides=['upnp/ssdp (shared)'],by=['Runtime']),
 n('bluez','ble/bluez','ble','a host adapter',provides=['raw Bluetooth: the router takes it'],by=['BluetoothAdapters']),
 n('cpchci','ble/silabs-cpc-hci','ble','the Bluetooth of a multi-PAN stick',provides=['raw Bluetooth: the router takes it'],by=['Radio']),
 n('proxy','BLEProxy','ble','ble/esphome-proxy: a device\'s radio lent to the router',provides=['raw Bluetooth: the router takes it'],
   by=['ESPhomeController (provides, per node with bluetooth_proxy)']),
 n('matter','MatterController','integrations','example: a service, an optional border router, Bluetooth',
   needs=['matter/matter-server','ble/router (optional)']),
 n('zigbee','ZigBeeController','integrations','example: a radio, directly',needs=['zigbee/ezsp · znp · deconz · …']),
 n('zwave','ZwaveController','integrations','example: a service on the stick',needs=['zwave/zwave-js-ws']),
 n('esphome','ESPhomeController','integrations','example: discovery, a border router, Bluetooth proxies',
   needs=['mdns/zeroconf','thread/otbr-rest (optional)','ble/router (optional)'],provides=['a BLEProxy per node']),
 n('homekit','HomeKitController','integrations','example: discovery only',needs=['mdns/zeroconf']),
]
NAME2ID={x['label']:x['id'] for x in N}
EMPH={'runtime','router'}
BOUNDARY={'compose','usb'}
STROKE={'runtime':'#3b4658'}
SECT={'runtime':(0,0),'hardware':(180,1),'drivers':(212,2),'services':(285,1),'providers':(80,1),'ble':(138,1),
'integrations':(0,1)}
RING={0:0,1:330,2:600}
RADJ={'hardware':40,'integrations':60,'services':-60,'providers':-60}
E=[
 *[('runtime',x,'own') for x in ['pinned','board','usb','btadapters','host','compose','router','zeroconf','ssdp']],
 ('usb','radio','own'),('board','radio','own'),('btadapters','bluez','own'),('radio','cpchci','own'),('esphome','proxy','own'),
 ('silabs','usb','impl'),('zwavedrv','usb','impl'),('zigpydrv','usb','impl'),
 ('radio','multipan','cmd'),('radio','otbr','cmd'),('radio','zjs','cmd'),('radio','zigbee','cmd'),
 ('compose','multipan','cmd'),('compose','otbr','cmd'),('compose','mjs','cmd'),('compose','zjs','cmd'),
 ('host','mjs','cmd'),('multipan','zigbee','cmd'),('mjs','matter','cmd'),('zjs','zwave','cmd'),
 ('zeroconf','esphome','cmd'),('zeroconf','homekit','cmd'),
 ('otbr','mjs','dot'),('multipan','mjs','dot'),('otbr','esphome','dot'),('router','matter','dot'),('router','esphome','dot'),
 ('bluez','router','dot'),('cpchci','router','dot'),('proxy','router','dot'),('bluez','mjs','dot'),
]
COLS={
'runtime':[['runtime']],
'hardware':[['btadapters','host','radio'],['pinned','board','usb']],
'drivers':[['silabs','zwavedrv','zigpydrv']],
'services':[['compose'],['multipan','otbr'],['mjs','zjs']],
'providers':[['router','zeroconf','ssdp']],
'ble':[['bluez','cpchci','proxy']],
'integrations':[['matter','zigbee','zwave','esphome','homekit']],
}
RELATIONS='''  <div class="lgroup"><span class="h">Relation</span><div class="lrow">
   <span class="li"><span class="ln" style="--x:#b6bdc8"></span>runs / brings along</span><span class="li"><span class="ln" style="--x:#0d8079"></span>serves a need</span>
   <span class="li"><span class="ln" style="--x:#b6bdc8;border-top-style:dotted"></span>serves an optional need</span><span class="li"><span class="ln dash" style="--x:#8a6fbf"></span>recognises sticks for</span>
   <span class="li"><span class="ln" style="--x:#2f81f7"></span><b>input (focus)</b></span><span class="li"><span class="ln" style="--x:#e08a2b"></span><b>output (focus)</b></span>
'''
PANEL={'inp':'Needs ◂ capabilities it is bound to','out':'Provides ▸ capabilities others need','dep':'Run by ▹ what brings it along',
'noout':'— nothing: it only consumes —','empty':'Click any peripheral to see what it needs, what it provides and what runs it.'}

if __name__ == "__main__":
    render("peripherals-map.html", "MajorDom — Peripherals Map", N=N, E=E, SECT=SECT, RING=RING, COLS=COLS, RADJ=RADJ,
           ANCHOR={}, SUPER={}, EMPH=EMPH, BOUNDARY=BOUNDARY, NAME2ID=NAME2ID, FILL=FILL, BORD=BORD, LABEL=LABEL,
           DOMAINS=list(LABEL), STROKE=STROKE, relations=RELATIONS, panel=PANEL)
