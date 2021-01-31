Update 30.01.2021:

Runtime now 171468 seconds, no single reboots. Code performs well.
- Fusion360 drawing for the the display at https://bit.ly/3ahuRlR
- Fusion360 drawing for the PMS7003 sensor at https://bit.ly/3j41YNR
- Fusion360 drawing for the MHZ19B sensor at https://bit.ly/2MckpnS
- ESP32 SMD and DevBoard drawings already in the same repository and at Thingsverse https://www.thingiverse.com/divergentti/designs


Update 29.01.2021:

Separated WifiConnect to own class as WIFICONN_AS.py. Do not try to transfer files with PyCharm to drivers directory! It does not change target directory \ to /.
Same with ampy, if you transder files, remember to use / instead of \. Example: ampy -p COM4 put drivers\WIFICONN_AS.py drivers/WIFICONN_AS.py works ok, but
if you use \, then you will see file in the root of filesystem named drivers\\WIFICONN_AS.py

Added Dew Point calculation to the main screen as well as altitude calculation. Changed white bottom line "touch and wait details" so that if Airqaulity is not ready, line do not show. This avoids null value screen, which is just skipped in the rotation loop if happens (try: expect: type error).

Added Sensor monitor, System monitor and Network monitor screen to the rotation.

MQTT listens broker uptime $SYS/broker/uptime messages and updates broker uptime value for the Network monitor screen.

REPL (and WebREPL) is silent if DEBUG_SCREEN_ACTIVE = 0.


Update 28.01.2021:

Strugled with mqtt client, because if you forget word "client" from async def mqtt_subscribe(client) sub, error message in MQTT_AS.py line 538 gave "function takes 0 positional arguments but 1 were given" error and I was too blind to see it. Now mqtt publish works fine and data can be collected to the inxludb and grafana. Continuing with screens. Available memory seems to hold somewhere in 20 000 range. 


27.01.2021.

This is first running version of indoor Airquality measurement device. 

Due to free ram issues variable names are refactored (shortened) and comments are removed from the code. I will update this README instead.

Operation:
- Hardware-related parameters are in the parameters.py. UART2 may have initialization problems if boot cause is power on boot. That is fixed in the code by deleting CO2 sensor object and re-creation of the object if bootcause was 1 = power on boot. For some reason 2 second pause is not enough, 5 seconds seems to work.
- Runtime-parameters are in runtimeconfig.json and my initial idea was to update this file so that user selections can be saved to the file. Now this file needs to be updated via WebREPl or via REPL.
- Network statup is asynhronous so that two SSID + PASSWORD combinations can be presented in the runtimeconfig.json. Highest rssi = signal strength AP is selected. Once network is connected = IP address is acquired, then script executes WebREPL startup and adjust time with NTPTIME. If network gets disconnected, script will redo network handshake.
- Measurement from all sensors are gathered in the background and values are filled into rows to be displayed.
- MQTT topics updates information to the broker and from broker to the InfluxDB and Grafana. 
- MQTT can be used to pick better correction multipliers for sensors.

Future:
- Add GPIO for the TFT panel LED control.
- Test if SD-slot can be used at the same time, with bit-banged softSPI for Touchscreen and hardware SPI for the SD-card.
- I try to add some trending, either so that trends are picked from Grafana as embedded graphics, or create some simple graphics, depending on free ram.
- Design case with Fusion360 to be printed with 3D-printer, adding proper air channels for sensors and perhaps litle Steveson's shield, which indoors is most likely not that important. BME280 sensor will be bottom, because heat from ESP32 SMD will go up. PMS7003 documentation recommends distance between floow and sensor > 20 cm, which means case shall be wall mounted. 
- Perhaps calculate better AirQuality etc information in the InfluxDB and return data back to device via MQTT.


Known issues:
- Due to memory allocation issues removed split screen to 4 parts, where from user was able to select next screen.
- Keyboard is not implemented, therefore touch just rotates detail screen (to be added more).
- Display update is slow due to framebuffer issue. During screen update availabe memory is low, may cause out of memory. I tried with Peter Hinch ILI9341 drivers, https://github.com/peterhinch/micropython-tft-gui and https://github.com/peterhinch/micropython-lcd160cr-gui but unfortunatelly with my knowledge I did not get driver working at all, resulting out of memory right in the class init. If you get them working, please, use those drivers instead of this slow driver.

Solved issues:
- Touchscreen gave strange x, y values: reason too high SPI-bus speed. Use minimum 1 MHz, maximum 2 MHz. This script uses 1.2MHz
- Toucscreen responded very slow to touch: bad DUPONT-connectors! 


Datasheets:
1. MH-Z19B CO2 NDIR sensor https://www.winsen-sensor.com/d/files/infrared-gas-sensor/mh-z19b-co2-ver1_0.pdf
2. BME280 Temp/Rh/Pressure sensor https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/
3. PMS7003 Particle sensor https://download.kamami.com/p564008-p564008-PMS7003%20series%20data%20manua_English_V2.5.pdf
4. ESP32 https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf

Libraries:
1. ILI9341 display rdagger / https://github.com/rdagger/micropython-ili9341/blob/master/ili9341.py
2. XGLCD fonts rdagger/ https://github.com/rdagger/micropython-ili9341/blob/master/xglcd_font.py
3. XPT2046 touchscreen  rdagger / https://github.com/rdagger/micropython-ili9341/blob/master/xpt2046.py
4. PMS7003_AS modified to asynchronous StreamReader method by Jari Hiltunen, 
   original Paweł Kucmus https://github.com/pkucmus/micropython-pms7003/blob/master/pms7003.py
5. MHZ19B_AS modified to asynchronous StreamWriter and Reader method by Jari Hiltunen, 
   original Dmytro Panin https://github.com/dr-mod/co2-monitoring-station/blob/master/mhz19b.py
6. MQTT_AS Peter Hinch / https://github.com/peterhinch/micropython-mqtt/blob/master/mqtt_as/mqtt_as.py

Micropython from https://micropython.org/ downloads https://micropython.org/download/ running esp32-idf4-20200902-v1.13.bin

AMPY tool for file transfers https://learn.adafruit.com/micropython-basics-load-files-and-run-code/install-ampy
