HA Gui based on Pyqt5 for slower/older machines (like RPI3, even older) with touch displays.


How to:
Instal python3 a create virtual environment:

Go to home directory, and run:

python3 -m venv venv

Activate environment from home diretory:

source venv/bin/activate

Install necessary packages:

sudo apt install python3-pyqtgraph
sudo apt install python3-websocket
sudo apt install python3-numpy

Pyqt5 can be installed via apt, and venv can use system libs:

Go to ~/venv directory

edit pyvenv.cfg

Change line:
include-system-site-packages = false 
to
include-system-site-packages = true

Install pyqt5 via apt:
sudo apt-get install python3-pyqt5  



Go to folder with a script and edit files:

config.ini

ha_token = long live token
ha_ip = change ip
ha_ip_ws = change ip
screen = no - can be "full" or "no"

entities_list.json contains list of "zones" and entities attached do this zones
Info about entietes:
{"entity_id": "light.z2m_przedpokoj_gora_tradfri", "name": "Przedpokoj", "widget_type": "light", "info_type": "light"},

entity_id = entity_id
name = your name 
widget_type:
  light = created for dimming lights (with temperature control or hue or both options)
    info_type:
      light = for only dimming lights
      temp_color = for lights with temperatur and color controls
      temp = for lights only with temperature control

widget_type:
  sensor_chart = created for sensors, will create button with sensor state for open graph 
  sensor= created for sensors, if graph is not needed
    info_type:
      window = for windows open/close sensors 
      doors = for doors open/close sensors
      temperature
      humadity
      binary = for different binary types
      generic = for all diffrent ones
      
widget_type:
  switch = for oridnary switches on/off
    info_type:
      switch
      
widget_type:
  number = for all entieties controled by numbers
    info_type:
      fan = for fan icon
      any other, no difference

widget_type:
  fan = for fan entieties
    info_type:
      fan = for fan icon
      any other, no difference
      
widget_type:      
      select = for select entieties
    info_type:
      list = for list icon
      any other, no difference  
  
      
      





