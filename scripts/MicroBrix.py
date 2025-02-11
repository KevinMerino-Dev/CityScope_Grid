import websocket
import rel
from time import sleep
import json
from threading import Thread

class MicroBrix():

    remote_host = 'cityio.media.mit.edu/cityio'
    geogrid_data = {}
    geogrid = {}

    def __init__(self, table_name=None,
            quietly=False,
            host_mode ='remote',
            host_name = None,
            core = False,
            core_name = None,
            core_description = None,
            core_category = None,
            keep_updating = False,
            update_interval = 5.0,
            module_function = None,
            save = False
    ):

        if host_name is None:
            self.host = self.remote_host
        else:
            self.host = host_name.strip('/')
        self.host = '127.0.0.1:8080' if host_mode=='local' else self.host

        self.quietly = quietly
        self.save = save
        self.keep_updating = keep_updating
        self.update_interval = update_interval
        self.table_name = table_name
        self.core = core
        self.core_name = core_name
        self.core_description = core_description
        self.core_category = core_category
        self.secure_protocol = '' if host_mode == 'local' else 's'
        self.front_end_url   = f'http{self.secure_protocol}://cityio-beta.media.mit.edu/?cityscope={self.table_name}'
        self.cityIO_post_url = f'http{self.secure_protocol}://{self.host}/api/table/{table_name}/'
        self.cityIO_list = f'http{self.secure_protocol}://{self.host}/api/table/list/'
        self.cityIO_wss = f'ws{self.secure_protocol}://{self.host}/module'
        if core:
            self.cityIO_wss = self.cityIO_wss + '/core'

        if(module_function == None):
            raise ValueError("module_function should contain a function that returns DeckGL layers")

        self.module_function = module_function

        if(not self.quietly):
            websocket.enableTrace(True)
        self.ws = websocket.WebSocketApp(
            self.cityIO_wss,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
            )

    def on_message(self, ws, message):
        dict_rec = json.loads(message)
        message_type = dict_rec['type']
        if(message_type == 'TABLE_SNAPSHOT'):
            table_name = dict_rec['content']['tableName']
            self.geogrid_data[table_name] = dict_rec['content']['snapshot']['GEOGRIDDATA']
            self.geogrid[table_name] = dict_rec['content']['snapshot']['GEOGRID']
            self.perform_update(table_name)
            thread = Thread(target = self.threaded_function, args = (table_name, ), daemon=True)
            thread.start()
        elif(message_type == 'GEOGRIDDATA_UPDATE'):
            print(dict_rec)
            table_name = dict_rec['content']['tableName']
            self.geogrid_data[table_name] = dict_rec['content']['geogriddata']
            self.perform_update(table_name)
        elif(self.core and message_type == 'SUBSCRIPTION_REQUEST'):
            requester = dict_rec['content']['table']
            self.send_message(json.dumps({"type":"SUBSCRIBE","content":{"gridId":requester}}))
        elif(self.core and message_type == 'SUBSCRIPTION_REMOVAL_REQUEST'):
            requester = dict_rec['content']['table']
            # self._clear_values(requester)
            self.send_message(json.dumps({"type":"UNSUBSCRIBE","content":{"gridId":requester}}))

    def on_error(self, ws, error):
        print(error)

    def on_close(self, ws, close_status_code, close_msg):
        print("## Connection closed")

    def on_open(self, ws):
        print("## Opened connection")
        if self.core:
            self.send_message(json.dumps({"type":"CORE_MODULE_REGISTRATION","content":{"name":self.core_name, "description": self.core_description, "moduleType":self.core_category}}))
        else:
            self.send_message(json.dumps({"type":"SUBSCRIBE","content":{"gridId":self.table_name}}))

    def send_message(self, message):
        self.ws.send(message)

    def threaded_function(self,table_name):
        if(self.keep_updating):
            while True:
                try:
                    sleep(self.update_interval)
                    self.perform_update(table_name)
                except:
                    continue

    def _send_indicators(self, layers, numeric, table):
        if(layers is not None and numeric is not None):
            message = {"type": "MODULE", "content":{"gridId": table, "save": self.save, "moduleData":{"layers":layers,"numeric":numeric}}}
        elif(layers is not None):
            message = {"type": "MODULE", "content":{"gridId": table, "save": self.save, "moduleData":{"layers":layers}}}
        elif(numeric is not None):
            message = {"type": "MODULE", "content":{"gridId": table, "save": self.save, "moduleData":{"numeric":numeric}}}

        self.send_message(json.dumps(message))

    def perform_update(self,table):
        layers, numeric = self.module_function(self.geogrid[table],self.geogrid_data[table])
        self._send_indicators(layers, numeric ,table)

    def listen(self):
        self.ws.run_forever(dispatcher=rel, reconnect=5)
        rel.signal(2, rel.abort)  # Keyboard Interrupt
        rel.dispatch()

    def stop(self):
        self.ws.close()
