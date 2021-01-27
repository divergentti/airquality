27.01.2020.

This is first running version of indoor Airquality measurement device. Due to free ram issues comments are removed from the code and I will update this README.

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


Known issues:
- Due to memory allocation issues removed split screen to 4 parts, where from user was able to select next screen.
- Keyboard is not implemented, therefore touch just rotates detail screen (to be added more).
- Display update is slow due to framebuffer issue. During screen update availabe memory is low, may cause out of memory. I tried with Peter Hinch ILI9341 drivers, https://github.com/peterhinch/micropython-tft-gui and https://github.com/peterhinch/micropython-lcd160cr-gui but unfortunatelly with my knowledge I did not get driver working at all, resulting out of memory right in the class init. If you get them working, please, use those drivers instead of this slow driver.


Datasheets:
1. MH-Z19B CO2 NDIR sensor https://www.winsen-sensor.com/d/files/infrared-gas-sensor/mh-z19b-co2-ver1_0.pdf
2. BME280 Temp/Rh/Pressure sensor https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/
3. PMS7003 Particle sensor https://download.kamami.com/p564008-p564008-PMS7003%20series%20data%20manua_English_V2.5.pdf


Libraries:
1. ILI9341 display rdagger / https://github.com/rdagger/micropython-ili9341/blob/master/ili9341.py
2. XGLCD fonts rdagger/ https://github.com/rdagger/micropython-ili9341/blob/master/xglcd_font.py
3. XPT2046 touchscreen  rdagger / https://github.com/rdagger/micropython-ili9341/blob/master/xpt2046.py
4. PMS7003_AS modified to asynchronous StreamReader method by Jari Hiltunen, 
   original Paweł Kucmus https://github.com/pkucmus/micropython-pms7003/blob/master/pms7003.py
5. MHZ19B_AS modified to asynchronous StreamWriter and Reader method by Jari Hiltunen, 
   original Dmytro Panin https://github.com/dr-mod/co2-monitoring-station/blob/master/mhz19b.py
6. MQTT_AS Peter Hinch / https://github.com/peterhinch/micropython-mqtt/blob/master/mqtt_as/mqtt_as.py