HA Gui based on Pyqt5 for slower/older machines (like RPI3 or even older) with touch displays.

(Short how to:
Instal python3 a create virtual environment:

Go to home directory, and run:
#python3 -m venv venv

Activate environment from home diretory:
#source venv/bin/activate

Install necessary packages:
#sudo apt install python3-pyqtgraph
#sudo apt install python3-websocket
#sudo apt install python3-numpy
#pip install pyqt-advanced-slider

Pyqt5 can be installed via apt, and venv can use system libs:

Go to ~/venv directory

edit pyvenv.cfg

Change line:
include-system-site-packages = false 
to
include-system-site-packages = true

Install pyqt5 via apt:
#sudo apt-get install python3-pyqt5  


Go to folder with a script and edit files:

config.ini
---------------------------------------------
ha_token = long live token  <br/>
ha_ip = change ip <br/>
ha_ip_ws = change ip <br/>
screen = can be "full" or "no" ("full" means: fullscreen without windows decorations)<br/>

entities_list.json 
---------------------------------------------
Contains list of "zones" and entities attached do this zones <br/>
Info about entietes: <br/>
{"entity_id": "light.z2m_przedpokoj_gora_tradfri", "name": "Przedpokoj", "widget_type": "light", "info_type": "light"},

entity_id = entity_id <br/>
name = your name  <br/>


widget_type: <br/>
  light = created for dimming lights (with temperature control or hue or both options) <br/>
    info_type: <br/>
      light = for only dimming lights <br/>
      temp_color = for lights with temperatur and color controls <br/>
      temp = for lights only with temperature control <br/>

widget_type:  <br/>
  sensor_chart = created for sensors, will create button with sensor state for open graph  <br/>
  sensor= created for sensors, if graph is not needed <br/>
    info_type: <br/>
      window = for windows open/close sensors  <br/>
      doors = for doors open/close sensors <br/>
      temperature <br/>
      humadity <br/>
      binary = for different binary types <br/>
      generic = for all diffrent ones <br/>
      
widget_type: <br/>
  switch = for oridnary switches on/off <br/>
    info_type: <br/>
      switch <br/>
      
widget_type: <br/>
  number = for all entieties controled by numbers <br/>
    info_type: <br/>
      fan = for fan icon <br/>
      any other, no difference <br/>



![Alt text](https://github.com/maskaz/ha_auto_py_gui/blob/main/screenshot_no_full_screen.png?raw=true "1")
![Alt text](https://github.com/maskaz/ha_auto_py_gui/blob/main/sensor_graph.png?raw=true "1")
