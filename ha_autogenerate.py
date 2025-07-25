import sys
import json
import threading
import websocket
import os
import os.path
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout,
    QSlider, QPushButton, QHBoxLayout, QScrollArea, QGroupBox, QScroller, QStyleOptionSlider, QDesktopWidget, QComboBox
)
from PyQt5.QtGui import QMouseEvent
from configparser import ConfigParser
from sensor_graph import show_sensor_graph  
from PyQt5.QtGui import QColor
from pyqt_advanced_slider import Slider
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel
        

def get_config_path():
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, "config.ini")

# Wczytywanie pliku konfiguracyjnego
config_path = get_config_path()
config_object = ConfigParser()
config_object.read(config_path)

if "ha" not in config_object:
    print("error config.ini!")
    sys.exit(1)

config = config_object["ha"]


HA_TOKEN = config["ha_token"]
HA_WS_URL = config["ha_ip_ws"]
screen_settings = config["screen"]



class ClickableSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle_rect = self.style().subControlRect(
                self.style().CC_Slider, opt,
                self.style().SC_SliderHandle, self)

            if not handle_rect.contains(event.pos()):
                value = self.minimum() + (
                    (self.maximum() - self.minimum()) * event.x()) / self.width()
                self.setValue(int(value))

                self.sliderReleased.emit()

        # Zachowaj domyślne zachowanie
        super().mousePressEvent(event)
        
        
def load_entity_groups_from_file():
    try:
        with open("entities_list.json", "r") as f:
            data = json.load(f)
            return data  
    except FileNotFoundError:
        print("no file")
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
                print(f"answer error: {msg.get('error')}")
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
        print("websocket closed")
        if self.on_disconnected:
            self.on_disconnected()

    def on_error(self, ws, error):
        self.connected = False
        print(f"error websocket: {error}")
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
        global screen_settings
        self.setWindowTitle("HAUI")
        self.setGeometry(100, 100, 600, 800)
        if ( screen_settings == "full"):
            self.setWindowFlag(Qt.FramelessWindowHint)
            self.showFullScreen()
            print("full screen")
        else:
           print("no full screen")
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



        self.debounce_timers = {}     



        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("switch_button")
        self.close_btn.setFixedHeight(50)
        self.close_btn.clicked.connect(self.close)
        self.main_layout.addWidget(self.close_btn)


    def select_changed(self, eid, combo):
        new_value = combo.currentText()
        print(f"Zmiana {eid} -> {new_value}")
        self.ha.call_service("select", "select_option", eid, {"option": new_value})
    
    def create_slider(self, min_val, max_val, eid, slot, height=40, radius=4):
        slider = Slider(self)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.setFixedHeight(height)
        slider.setBorderRadius(radius)
        slider.setTextColor(QColor("transparent"))
        slider.setBackgroundColor(QColor.fromRgb(64, 64, 64))
        slider.setAccentColor(QColor('#f6825d'))
        slider.setBorderColor(QColor.fromRgb(0, 0, 0))
        slider.entity_id = eid
        slider.valueChanged.connect(slot)
        return slider
    

    def show_temp_popup(self, eid, itype, name):
        self.popup = QWidget()
        vbox_layout = QVBoxLayout(self.popup)

        frame_geometry = self.popup.frameGeometry()
        screen_center = QDesktopWidget().availableGeometry().center()
        frame_geometry.moveCenter(screen_center)
        self.popup.move(frame_geometry.topLeft())
    

        slider_temp = self.create_slider(200, 400, eid, self.slider_released_temp, radius=3)


        current_value = self.ha.entity_states.get(eid, {}).get("attributes", {}).get("color_temp")
        if current_value == None:
           current_value = 300
        slider_temp.setValue(int(current_value))


        self.entity_info_types[(eid, "temp")] = itype
        self.entity_widgets[(eid, "temp")] = slider_temp

        label_name = QLabel(f"{name} Temperature")
        vbox_layout.addWidget(label_name)
        vbox_layout.addWidget(slider_temp) 
        
        label_vis = QLabel()
        label_vis.setFixedHeight(30)
        label_vis.setStyleSheet("""
        QLabel {
        color: white;
        padding: 1px;
        border-radius: 2px;
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 #ffffff,
            stop: 1 #ff8600
        );
        }
        """)        
        vbox_layout.addWidget(label_vis)
        
        btn_close = QPushButton("Close")
        btn_close.setObjectName("switch_button")
        btn_close.clicked.connect(self.popup.close)
        vbox_layout.addWidget(btn_close)
        
        self.popup.setLayout(vbox_layout)
        self.popup.resize(600, 200)
        self.popup.show()

    def show_color_popup(self, eid, itype, name):
        self.popup = QWidget()
        vbox_layout = QVBoxLayout(self.popup)


        frame_geometry = self.popup.frameGeometry()
        screen_center = QDesktopWidget().availableGeometry().center()
        frame_geometry.moveCenter(screen_center)
        self.popup.move(frame_geometry.topLeft())
        
        slider_hue = self.create_slider(40, 350, eid, self.slider_released_hue, radius=3)



        current_value = self.ha.entity_states.get(eid, {}).get("attributes", {}).get("hs_color", 200)
        current_value = current_value[0]
        slider_temp.setValue(int(current_value))


        self.entity_info_types[(eid, "temp")] = itype
        self.entity_widgets[(eid, "temp")] = slider_temp

        label_ = QLabel(f"{name} Hue")
        vbox_layout.addWidget(label_)
        vbox_layout.addWidget(slider_temp)
        
        label_vis = QLabel()
        label_vis.setFixedHeight(30)
        label_vis.setStyleSheet("""
        QLabel {
        color: white;
        padding: 1px;
        border-radius: 2px;
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 #ff8600,
            stop: 0.1 #f2ff00,
            stop: 0.23 #00ff04,
            stop: 0.4 #00eeff,
            stop: 0.56 #0009ff,
            stop: 0.83 #fd00ff,
            stop: 1 #ff0000
        );
        }
        """)        
        vbox_layout.addWidget(label_vis)
        
        btn_close = QPushButton("Close")
        btn_close.setObjectName("switch_button")
        btn_close.clicked.connect(self.popup.close)
        vbox_layout.addWidget(btn_close)
        
        self.popup.setLayout(vbox_layout)
        self.popup.resize(600, 200)
        self.popup.show()

     
        
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

                
                if itype == "light":
                    icon = f"󰌵"
                elif itype == "temp":
                    icon = f"󰌵"
                elif itype == "switch":
                    icon = f"󱨤"
                elif itype == "temperature":
                    icon = f"󰔄"
                elif itype == "humadity":
                    icon = f"󰖎"
                elif itype == "window":
                    icon = f"󱇛"
                elif itype == "doors":
                    icon = f"󰠚"
                elif itype == "cover":
                    icon = f"󱡇"
                elif itype == "presence":
                    icon = f"󰙍"
                elif itype == "fan":
                    icon = f"󰫕"
                elif itype == "audio":
                    icon = f"󰓃"
                elif itype == "list":
                    icon = f"󱭼"                    
                else:
                    icon = f"󰞱"


                label = QLabel(icon)
                label.setObjectName("ico")
                label.setFixedWidth(30)
                label.setFixedHeight(30)
                label.setAlignment(Qt.AlignHCenter)
                hbox.addWidget(label)
                
                if itype == "temp":
                   name = f"{name} "
                   label_ = QLabel(name)
                   label_.setFixedWidth(140)
                   hbox.addWidget(label_)                                 
                                
                else:
                   label_ = QLabel(name)
                   label_.setFixedWidth(140)
                   hbox.addWidget(label_)                                 
                
                
                if etype == "light":


                    vbox = QWidget()
                    vbox_layout = QVBoxLayout(vbox)
                    hbox.addWidget(vbox)
                    vbox_layout.setContentsMargins(0, 0, 0, 0) 
                    vbox_layout.setSpacing(0)                    

                    
                    slider = self.create_slider(0, 255, eid, self.slider_released, radius=3)
                    vbox_layout.addWidget(slider)
                    
                    self.entity_info_types[(eid, "brightness")] = itype
                    self.entity_widgets[(eid, "brightness")] = slider
                    
                    Hbox = QWidget()
                    Hbox_layout = QHBoxLayout(Hbox)
                    Hbox_layout.setContentsMargins(0, 10, 0, 0)  # top, left, bottom, right
                    Hbox_layout.setSpacing(0)
                    vbox_layout.addWidget(Hbox)      

                    
                    
                    if itype == "temp":
                       btn_hue = QPushButton("Temperature")
                       btn_hue.setObjectName("switch_button")
                       btn_hue.setFixedSize(120, 40)
                       btn_hue.clicked.connect(lambda _, eid=eid, itype="temp", name=name: self.show_temp_popup(eid, itype, name))
                       Hbox_layout.addWidget(btn_hue)

                    if itype == "temp_color":

                       btn_hue = QPushButton("Temperature")
                       btn_hue.setFixedSize(120, 40)
                       btn_hue.setObjectName("switch_button")
                       btn_hue.clicked.connect(lambda _, eid=eid, itype="temp", name=name: self.show_temp_popup(eid, itype, name))
                       Hbox_layout.addWidget(btn_hue)
                       btn_Hue = QPushButton("Hue")
                       btn_Hue.setObjectName("switch_button")
                       btn_Hue.setFixedSize(120, 40)
                       btn_Hue.clicked.connect(lambda _, eid=eid, itype="temp_color", name=name: self.show_color_popup(eid, itype, name))
                       Hbox_layout.addWidget(btn_Hue)

                    
                    
                elif etype == "switch":
                    button = QPushButton("On")
                    button.setObjectName("switch_button")
                    button.clicked.connect(lambda _, eid=eid: self.toggle_switch(eid))
                    hbox.addWidget(button)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = button

                elif etype == "cover":
                    slider = self.create_slider(0, 100, eid, self.cover_slider_released)
                    hbox.addWidget(slider)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = slider

                elif etype == "fan":
                    slider = self.create_slider(0, 100, eid, self.fan_slider_released)
                    hbox.addWidget(slider)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = slider
                    
                elif etype == "number":
                    value_layout = QHBoxLayout()
                    value_widget = QWidget()
                    value_widget.setLayout(value_layout)
                    btn_minus = QPushButton("󱘹")
                    btn_minus.setFixedSize(80, 40)
                    btn_minus.setObjectName("switch_button")
                    value_layout.addWidget(btn_minus)
                    value_label = QLabel("...")
                    value_label.setFixedWidth(60)
                    value_label.setAlignment(Qt.AlignCenter)
                    value_label.setObjectName("label")
                    value_layout.addWidget(value_label)
                    btn_plus = QPushButton("󰿶")
                    btn_plus.setFixedSize(80, 40)
                    btn_plus.setObjectName("switch_button")
                    value_layout.addWidget(btn_plus)
                    hbox.addWidget(value_widget)
                    self.entity_widgets[(eid, "label")] = value_label
                    self.entity_info_types[eid] = itype
                    btn_minus.clicked.connect(lambda _, eid=eid: self.adjust_number_value(eid, -1))
                    btn_plus.clicked.connect(lambda _, eid=eid: self.adjust_number_value(eid, 1))
    
                    
                elif etype == "sensor_chart":
                    button = QPushButton("...")
                    button.setObjectName("sensor_chart_button")
                    button.clicked.connect(lambda _, eid=eid: self.toggle_sensor_chart(eid))
                    hbox.addWidget(button)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = button

                elif etype == "sensor" or etype == "binary_sensor":
                    value_label = QLabel("...")
                    value_label.setObjectName("label")
                    hbox.addWidget(value_label)
                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = value_label

                elif etype == "select":
                    combo = QComboBox()
                    combo.setFixedHeight(40)
                    combo.setObjectName("select_combo")
                    combo.entity_id = eid
                    combo.currentIndexChanged.connect(lambda _, eid=eid, combo=combo: self.select_changed(eid, combo))
                    hbox.addWidget(combo)

                    self.entity_info_types[eid] = itype
                    self.entity_widgets[eid] = combo
    
                group_layout.addWidget(container)

            self.container_layout.addWidget(group_box)


    def adjust_number_value(self, eid, direction):
        state_obj = self.ha.entity_states.get(eid)
        if not state_obj:
            print(f"no entity state {eid}")
            return
    
        attrs = state_obj.get("attributes", {})
        try:
            current = float(state_obj.get("state", 0))
            step = float(attrs.get("step", 1))    
            min_ = float(attrs.get("min", 0))
            max_ = float(attrs.get("max", 100))
        except (ValueError, TypeError) as e:
            print(f"atrr error {eid}: {e}")
            return

        new_value = current + direction * step
        new_value = max(min_, min(max_, new_value)) 

        self.ha.call_service("number", "set_value", eid, {"value": new_value})
    
    def update_entity_state(self, eid, state_obj):
        # Jasność slider
        brightness_widget = self.entity_widgets.get((eid, "brightness"))
        temp_widget = self.entity_widgets.get((eid, "temp"))
        hue_widget = self.entity_widgets.get((eid, "hue"))
        generic_widget = self.entity_widgets.get(eid)  

        itype = self.entity_info_types.get(eid, "")
        state = state_obj.get("state")
        attrs = state_obj.get("attributes", {})


        if eid.startswith("light."):
            if brightness_widget:
                brightness = 0 if state == "off" else int(attrs.get("brightness", 0))
                brightness_widget.blockSignals(True)
                brightness_widget.setValue(brightness)
                brightness_widget.blockSignals(False)

            if temp_widget:
                temp = attrs.get("color_temp")
                print(temp)
                if isinstance(temp, (int, float)):
                    temp_widget.blockSignals(True)
                    temp_widget.setValue(int(temp))
                    temp_widget.blockSignals(False)

            if hue_widget:
                hue = attrs.get("hue")
                if isinstance(temp, (int, float)):
                    hue_widget.blockSignals(True)
                    hue_widget.setValue(int(hue))
                    hue_widget.blockSignals(False)
                    
        elif eid.startswith("switch."):
            if generic_widget:
                generic_widget.setText("Off" if state == "on" else "On")

        elif eid.startswith("cover."):
            if generic_widget:
                position = int(attrs.get("current_position", 0))
                generic_widget.blockSignals(True)
                generic_widget.setValue(position)
                generic_widget.blockSignals(False)

        elif eid.startswith("fan."):
            if generic_widget:
                position = int(attrs.get("percentage", 0))
                generic_widget.blockSignals(True)
                generic_widget.setValue(position)
                generic_widget.blockSignals(False)
                
        elif eid.startswith("sensor_chart."):
            if generic_widget:
                generic_widget.setText(str(state))

        elif eid.startswith("sensor.") or eid.startswith("binary_sensor."):
            if generic_widget:
                if "doors" in itype or "window" in itype:
                    state = "Open" if state == "on" else "Closed"
                if "Presence" in itype:
                    state = "Presence" if state == "on" else "No presence"
                generic_widget.setText(str(state))

        elif eid.startswith("number."):
            label = self.entity_widgets.get((eid, "label"))
            if label:
                try:
                    label.setText(f"{float(state):.0f}")
                except:
                    label.setText(state)


        elif eid.startswith("select."):
            if isinstance(generic_widget, QComboBox):
                options = attrs.get("options", [])
                current = state

                generic_widget.blockSignals(True)
                generic_widget.clear()
                generic_widget.addItems(options)
                if current in options:
                    index = options.index(current)
                    generic_widget.setCurrentIndex(index)
                generic_widget.blockSignals(False)
        
    def slider_released(self, value):
        slider = self.sender()
        eid = slider.entity_id
        brightness = value
        
        if eid in self.debounce_timers:
            self.debounce_timers[eid].stop()
        
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda eid=eid, brightness=brightness: self.send_slider_value(eid, brightness))
        self.debounce_timers[eid] = timer
        timer.start(300)  

    def slider_released_temp(self, value):
        slider = self.sender()
        eid = slider.entity_id
        temp = value
        
        if eid in self.debounce_timers:
            self.debounce_timers[eid].stop()
        
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda eid=eid, temp=temp: self.send_slider_value_temp(eid, temp))
        self.debounce_timers[eid] = timer
        timer.start(300)  

    def slider_released_hue(self, value):
        slider = self.sender()
        eid = slider.entity_id
        hue = value
        
        if eid in self.debounce_timers:
            self.debounce_timers[eid].stop()
        
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda eid=eid, hue=hue: self.send_slider_value_hue(eid, hue))
        self.debounce_timers[eid] = timer
        timer.start(300)  
        
        
    def send_slider_value(self, eid, brightness):
        if brightness > 0:
            self.ha.call_service("light", "turn_on", eid, {"brightness": brightness})
        else:
            self.ha.call_service("light", "turn_off", eid)
        if eid in self.debounce_timers:
          del self.debounce_timers[eid]

    def send_slider_value_temp(self, eid, temp):
        self.ha.call_service("light", "turn_on", eid, {"color_temp": temp})
        if eid in self.debounce_timers:
          del self.debounce_timers[eid]
          
    def send_slider_value_hue(self, eid, hue):
        self.ha.call_service("light", "turn_on", eid, {"hs_color": [hue, 100]})
        if eid in self.debounce_timers:
          del self.debounce_timers[eid]
          
    def send_cover_slider_value(self, eid, position):
        self.ha.call_service("cover", "set_cover_position", eid, {"position": position})
        if eid in self.debounce_timers:
          del self.debounce_timers[eid]
          
    def send_fan_slider_value(self, eid, position):
        print("fan")
        self.ha.call_service("fan", "set_percentage", eid, {"percentage": position})
        if eid in self.debounce_timers:
          del self.debounce_timers[eid]
          
    def cover_slider_released(self, value):
        slider = self.sender()
        eid = slider.entity_id
        position = value
        
        if eid in self.debounce_timers:
            self.debounce_timers[eid].stop()
        
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda eid=eid, position=position: self.send_cover_slider_value(eid, position))
        self.debounce_timers[eid] = timer
        timer.start(300)  

    def fan_slider_released(self, value):
        slider = self.sender()
        eid = slider.entity_id
        position = value
        
        if eid in self.debounce_timers:
            self.debounce_timers[eid].stop()
        
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda eid=eid, position=position: self.send_fan_slider_value(eid, position))
        self.debounce_timers[eid] = timer
        timer.start(300) 
        
        
        
    def toggle_switch(self, eid):
        state = self.ha.entity_states.get(eid, {}).get("state")
        service = "turn_off" if state == "on" else "turn_on"
        self.ha.call_service("switch", service, eid)

    def toggle_sensor_chart(self, eid):
        if hasattr(self, "graph_window") and self.graph_window.isVisible():
            print("already open")
        else:
            self.graph_window = show_sensor_graph(eid)
            self.graph_window.show()
            self.graph_window.raise_()
            self.graph_window.activateWindow()

    def handle_disconnected(self):
        if not self.reconnect_timer.isActive():
            print("another try after 10 seconds")
            self.reconnect_timer.start(10000)

    def try_reconnect(self):
        if not self.ha.connected:
            print("reconnecting with HA")
            self.ha.connect()
        else:
            self.reconnect_timer.stop()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HAControlUI()
    window.show()
    sys.exit(app.exec_())

