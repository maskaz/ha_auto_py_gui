import sys
import math
import os
import numpy as np
from datetime import datetime, timedelta
import requests
from configparser import ConfigParser

from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
import pyqtgraph as pg

config_object = ConfigParser()

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
config_object.read(config_path)

config_object.read(config_path)
config = config_object["ha"]


HA_TOKEN = config["ha_token"]
HA_URL = config["ha_ip"]


def load_stylesheet(path):
    with open(path, "r") as file:
        return file.read()
        
class VerticalAxis(pg.AxisItem):
    def __init__(self, orientation='bottom'):
        super().__init__(orientation=orientation)
        self._angle = -90  # obrót etykiety
        self._height_updated = False

    def tickStrings(self, values, scale, spacing):
        return [datetime.fromtimestamp(value).strftime("%H:%M") for value in values]

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        super().drawPicture(p, axisSpec, tickSpecs, [])
        font = QFont("Arial", 10)
        p.setFont(font)
        p.setPen(self.pen())

        max_width = 0
        self._angle = self._angle % -180

        for rect, flags, text in textSpecs:
            p.save()

            p.translate(rect.center())
            p.rotate(self._angle)
            p.translate(-rect.center())

            x_offset = math.ceil(math.fabs(math.sin(math.radians(self._angle)) * rect.width()))
            if self._angle < 0:
                x_offset = -x_offset

            p.translate(x_offset / 2, 0)
            p.drawText(rect, flags, text)
            p.restore()

            offset = math.fabs(x_offset)
            max_width = offset if max_width < offset else max_width

        if not self._height_updated:
            self.setHeight(self.height() + max_width)
            self._height_updated = True


def get_sensor_history(sensor_id):
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }

    meta_url = f"{HA_URL}/api/states/{sensor_id}"
    meta_response = requests.get(meta_url, headers=headers)
    if meta_response.status_code != 200:
        raise Exception(f"nie udalo sie pobrac metadanych sensora: {meta_response.status_code}")
    meta_data = meta_response.json()

    is_binary = sensor_id.startswith("binary_sensor.") or meta_data.get("attributes", {}).get("device_class") in ["window", "door", "opening"]

    now_utc = datetime.utcnow()
    now = now_utc + timedelta(hours=2)  
    start = now - timedelta(hours=6)
    start_iso = start.isoformat()
    end_iso = now.isoformat()

    url = f"{HA_URL}/api/history/period/{start_iso}?end_time={end_iso}&filter_entity_id={sensor_id}&significant_changes=true"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"blad pobierania danych: {response.status_code} – {response.text}")

    data = response.json()
    timestamps, values = [], []

    for entry in data[0]:
        try:
            timestamp = datetime.fromisoformat(entry['last_updated'].replace('Z', '+00:00'))
            state_str = entry['state'].lower()

            if is_binary:
                state_map = {"on": 1, "off": 0, "open": 1, "closed": 0}
                if state_str in state_map:
                    value = state_map[state_str]
                else:
                    continue
            else:
                value = float(entry['state'])

            timestamps.append(timestamp)
            values.append(value)
        except (ValueError, KeyError):
            continue

    return timestamps, values, is_binary


class SensorChartWindow(QMainWindow):
    def __init__(self, sensor_id):
        super().__init__()
        self.setWindowTitle(f"Wykres: {sensor_id}")
        self.resize(1000, 600)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.showFullScreen()
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        self.stylesheet = load_stylesheet("style.qss")
        self.setStyleSheet(self.stylesheet)
        
        
        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("font-size: 12px; padding: 5px;")
        layout.addWidget(self.info_label)

        self.plot_widget = pg.PlotWidget(axisItems={'bottom': VerticalAxis(orientation='bottom')})
        layout.addWidget(self.plot_widget)

        self.plot = self.plot_widget.getPlotItem()
        self.plot.showGrid(x=True, y=True)
     #   self.plot.setLabel('left', 'Wartość')
     #   self.plot.setLabel('bottom', 'Czas')

        self.sensor_id = sensor_id
        self.update_interval = 60
        self.seconds_left = self.update_interval
        self.is_binary = False

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)

        close_btn = QPushButton("Zamknij")
        close_btn.setObjectName("switch_button")
        close_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        close_btn.setFixedHeight(60)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.refresh_data()

    def refresh_data(self):
        try:
            self.timestamps, self.values, self.is_binary = get_sensor_history(self.sensor_id)
        except Exception as e:
            print(f"blad pobierania danych: {e}")
            self.timestamps, self.values, self.is_binary = [], [], False

        self.update_plot()
        self.seconds_left = self.update_interval

    def update_plot(self):
        if not self.timestamps or not self.values:
            self.plot.clear()
            self.info_label.setText("brak danych do wyswietlenia")
            return

        x = np.array([ts.timestamp() for ts in self.timestamps], dtype=float)
        y = np.array(self.values, dtype=float)

        self.plot.clear()

        if self.is_binary:
            if len(x) > 1:
                delta = x[-1] - x[-2]
            else:
                delta = 60
            x_extended = np.append(x, x[-1] + delta)

            self.plot.plot(x_extended, y, stepMode=True, fillLevel=0, brush=(0, 128, 255, 100), pen=pg.mkPen(color='#0077CC', width=2))
            ticks = [(0, "OFF"), (1, "ON")]
            self.plot.getAxis('left').setTicks([ticks])
            self.plot.setYRange(-0.1, 1.1)
        else:
            self.plot.plot(x, y, pen=pg.mkPen(color='#1c9bf0', width=2))
            min_val = np.min(y)
            max_val = np.max(y)
            margin = (max_val - min_val) * 0.1 if max_val != min_val else 1
        #    self.plot.setYRange(min_val - margin, max_val + margin)

        max_ticks = 10
        total_points = len(self.timestamps)

        if total_points <= max_ticks:
            ticks = [(ts.timestamp(), datetime.fromtimestamp(ts.timestamp()).strftime("%H:%M")) for ts in self.timestamps]
        else:
            step = max(1, total_points // max_ticks)
            ticks = [(ts.timestamp(), datetime.fromtimestamp(ts.timestamp()).strftime("%H:%M"))
                     for i, ts in enumerate(self.timestamps) if i % step == 0]

        self.plot.getAxis('bottom').setTicks([ticks])

        now = datetime.now().strftime("%H:%M")
        self.info_label.setText(f"{self.sensor_id} | Ostatnia aktualizacja: {now} | Odswiezenie za: {self.seconds_left}s")

    def update_countdown(self):
        self.seconds_left -= 1
        if self.seconds_left <= 0:
            self.refresh_data()
        else:
            now = datetime.now().strftime("%H:%M")
            self.info_label.setText(f"{self.sensor_id} | Ostatnia aktualizacja: {now} | Odswiezenie za: {self.seconds_left}s")


def show_sensor_graph(sensor_id: str):
    app = QApplication.instance()
    created_app = False

    if app is None:
        app = QApplication(sys.argv)
        created_app = True

    window = SensorChartWindow(sensor_id)
    window.show()

    if created_app:
        sys.exit(app.exec_())

    return window

