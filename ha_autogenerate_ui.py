import sys
import json
import threading
import websocket
import os
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout,
    QSlider, QPushButton, QHBoxLayout, QScrollArea, QGroupBox, QScroller
)
from configparser import ConfigParser
from sensor_graph import show_sensor_graph  


config_object = ConfigParser()

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
config_object.read(config_path)

config_object.read(config_path)
config = config_object["ha"]


HA_TOKEN = config["ha_token"]
HA_WS_URL = config["ha_ip_ws"]


def load_entity_groups_from_file():
    try:
        with open("entities.json", "r") as f:
            data = json.load(f)
            return data  
    except FileNotFoundError:
        print("brak pliku")
        return {}

def load_stylesheet(path):
    with open(path, "r") as file:
        return file.read()
        
        
class HAWebSocketClient:
    def __init__(self, on_state_update, on_disconnected=None):
        self.ws = None
        self.authenticated = False
        self.connected = False
        self.msg_id = 1
        self.entity_states = {}
        self.on_state_update = on_state_update
        self.on_disconnected = on_disconnected


    def connect(self):
        def run():
            self.ws = websocket.WebSocketApp(
                HA_WS_URL,
                on_open=self.on_open,
                on_message=self.on_message,
                on_close=self.on_close,
                on_error=self.on_error
            )
            self.ws.run_forever()
        threading.Thread(target=run, daemon=True).start()

    def send(self, payload):
        if self.connected:
            try:
                self.ws.send(json.dumps(payload))
            except Exception as e:
                print(f"blad wysylania: {e}")

    def next_id(self):
        self.msg_id += 1
        return self.msg_id

    def on_open(self, ws):
        self.connected = True
        print("polaczono z HA")
        self.send({"type": "auth", "access_token": HA_TOKEN})

    def on_message(self, ws, message):
        try:
            msg = json.loads(message)
        except json.JSONDecodeError:
            print("bledny JSON:", message)
            return

        if msg["type"] == "auth_ok":
            self.authenticated = True
            self.subscribe_events()
            self.get_initial_states()

        elif msg["type"] == "event":
            entity_id = msg["event"]["data"]["entity_id"]
            new_state = msg["event"]["data"]["new_state"]
            self.entity_states[entity_id] = new_state
            self.on_state_update(entity_id, new_state)

        elif msg["type"] == "result":
            if not msg.get("success"):
                print(f"blad odpowiedzi: {msg.get('error')}")
                return

            result = msg.get("result")
            if result is None:
                return

            if isinstance(result, dict) and "entity_id" in result:
                eid = result["entity_id"]
                self.entity_states[eid] = result
                self.on_state_update(eid, result)

            elif isinstance(result, list):
                for state in result:
                    eid = state.get("entity_id")
                    if eid:
                        self.entity_states[eid] = state
                        self.on_state_update(eid, state)

    def on_close(self, ws, *args):
        self.connected = False
        print("websocket zamkniety")
        if self.on_disconnected:
            self.on_disconnected()

    def on_error(self, ws, error):
        self.connected = False
        print(f"blad websocket: {error}")
        if self.on_disconnected:
            self.on_disconnected()

    def subscribe_events(self):
        self.send({
            "id": self.next_id(),
            "type": "subscribe_events",
            "event_type": "state_changed"
        })

    def get_initial_states(self):
        self.send({
            "id": self.next_id(),
            "type": "get_states"
        })

    def call_service(self, domain, service, entity_id, data=None):
        if data is None:
            data = {}
        data["entity_id"] = entity_id
        self.send({
            "id": self.next_id(),
            "type": "call_service",
            "domain": domain,
            "service": service,
            "service_data": data
        })


class HAControlUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sterowanie HA")
        self.setGeometry(100, 100, 600, 800)
    #    self.setWindowFlag(Qt.FramelessWindowHint)
    #    self.showFullScreen()
        self.stylesheet = load_stylesheet("style.qss")
        app.setStyleSheet(self.stylesheet)


        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)


        self.main_layout = QVBoxLayout(self.central_widget)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.LeftMouseButtonGesture)
        self.main_layout.addWidget(self.scroll_area)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.container)

        self.entity_widgets = {}
        self.entity_groups = load_entity_groups_from_file()

        self.entity_info_types = {}


        self.ha = HAWebSocketClient(
            on_state_update=self.update_entity_state,
            on_disconnected=self.handle_disconnected
        )
        self.ha.connect()

        self.setup_widgets()

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.try_reconnect)

        self.close_btn = QPushButton("Zamknij")
        self.close_btn.setObjectName("switch_button")
        self.close_btn.setFixedHeight(50)
        self.close_btn.clicked.connect(self.close)
        self.main_layout.addWidget(self.close_btn)

     



        
        
    def setup_widgets(self):
        for group_name, entities in self.entity_groups.items():
            group_box = QGroupBox(group_name)

            group_layout = QVBoxLayout()
            group_box.setLayout(group_layout)

            for entity in entities:
                eid = entity["entity_id"]
                etype = entity["widget_type"]
                itype = entity["info_type"]
                name = entity["name"]
                

                container = QWidget()
                hbox = QHBoxLayout()
                container.setLayout(hbox)

                label = QLabel(name)
                label.setFixedWidth(200)
                hbox.addWidget(label)

                 
                
                
                if etype == "light":
                    slider = QSlider(Qt.Horizontal)
                    slider.setMinimum(0)
                    slider.setFixedHeight(30)
                
                    slider.setMaximum(255)
                    slider.entity_id = eid
                    slider.sliderReleased.connect(self.slider_released)
                    hbox.addWidget(slider)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = slider

                elif etype == "switch":
                    button = QPushButton("Wlacz")
                    button.setObjectName("switch_button")
                    button.clicked.connect(lambda _, eid=eid: self.toggle_switch(eid))
                    hbox.addWidget(button)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = button

                elif etype == "cover":
                    # zamiast przycisku cover dajemy slider 0-100
                    slider = QSlider(Qt.Horizontal)
                    slider.setFixedHeight(30)
                    slider.setMinimum(0)
                    slider.setMaximum(100)
                    slider.entity_id = eid
                    slider.sliderReleased.connect(self.cover_slider_released)
                    hbox.addWidget(slider)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = slider

                elif etype == "sensor_chart":
                    button = QPushButton("...")
                    button.setObjectName("sensor_chart_button")

                    button.clicked.connect(lambda _, eid=eid: self.toggle_sensor_chart(eid))
                    hbox.addWidget(button)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = button

                elif etype == "sensor" or etype == "binary_sensor":
                    value_label = QLabel("...")
                    
                    hbox.addWidget(value_label)
                    
                    value_label.setObjectName("label")
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = value_label

                group_layout.addWidget(container)

            self.container_layout.addWidget(group_box)

    def update_entity_state(self, eid, state_obj):
        if eid not in self.entity_widgets:
            return

        itype = self.entity_info_types.get(eid, "")
        print(eid)
        print(itype)
        widget = self.entity_widgets[eid]
        state = state_obj.get("state")

        if eid.startswith("light."):
            brightness = 0 if state == "off" else int(state_obj.get("attributes", {}).get("brightness", 0))
            widget.blockSignals(True)
            widget.setValue(brightness)
            widget.blockSignals(False)

        elif eid.startswith("switch."):
            widget.setText("Wylacz" if state == "on" else "Wlacz")

        elif eid.startswith("cover."):
            position = int(state_obj.get("attributes", {}).get("current_position", 0))
            widget.blockSignals(True)
            widget.setValue(position)
            widget.blockSignals(False)

        elif eid.startswith("sensor_chart."):
            widget.setText(str(state))

        elif eid.startswith("sensor.") or eid.startswith("binary_sensor."):
            if "drzwi_okna" in itype:
                state = "Otwarte" if state == "on" else "Zamkniete"
            if "obecnosc" in itype:
                state = "Ktos sie kreci" if state == "on" else "Brak"
            widget.setText(str(state))

    def slider_released(self):
        slider = self.sender()
        eid = slider.entity_id
        brightness = slider.value()

        if brightness > 0:
            self.ha.call_service("light", "turn_on", eid, {"brightness": brightness})
        else:
            self.ha.call_service("light", "turn_off", eid)

    def cover_slider_released(self):
        slider = self.sender()
        eid = slider.entity_id
        position = slider.value()
        self.ha.call_service("cover", "set_cover_position", eid, {"position": position})

    def toggle_switch(self, eid):
        state = self.ha.entity_states.get(eid, {}).get("state")
        service = "turn_off" if state == "on" else "turn_on"
        self.ha.call_service("switch", service, eid)

    def toggle_sensor_chart(self, eid):
        if hasattr(self, "pierwsze_window") and self.pierwsze_window.isVisible():
            print("wykres juz otwarty")
        else:
            self.pierwsze_window = show_sensor_graph(eid)
            self.pierwsze_window.show()
            self.pierwsze_window.raise_()
            self.pierwsze_window.activateWindow()

    def handle_disconnected(self):
        if not self.reconnect_timer.isActive():
            print("za 10 sekund proba polaczenia")
            self.reconnect_timer.start(10000)

    def try_reconnect(self):
        if not self.ha.connected:
            print("ponowne laczenie z HA")
            self.ha.connect()
        else:
            self.reconnect_timer.stop()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HAControlUI()
    window.show()
    sys.exit(app.exec_())

