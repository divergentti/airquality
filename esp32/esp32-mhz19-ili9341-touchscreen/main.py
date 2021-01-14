""""

This script is used for airquality measurement. Display is ILI9341 2.8" TFT touch screen in the SPI bus,
CO2 device is MH-Z19 NDIR-sensor, particle sensor is PMS7003 and temperature/rh/pressure sensor BME280.

Boot.py does not setup network. If user wants to connect to the network and to the mqtt-server, that can be done
from the display either with predefined SSID name and password, or password for accessible networks.


Libraries:
1. MQTT_AS https://github.com/peterhinch/micropython-mqtt/blob/master/mqtt_as/mqtt_as.py
2. MHZ19B.py in this blob
3. ILI9341 display, touchscreen, fonts and keyboard https://github.com/rdagger/micropython-ili9341
   You may drive display LED from GPIO if display has transistor in the LED pin. Otherwise connect LED to 3.3V

!! DO NOT USE PyCharm to upload fonts or images to the ESP32! Use command ampy -p COMx directoryname instead!
   PyCharm can not handle directories in ESP32. For some reason it combines name of the directory and file to one file.


13.01.2020: Jari Hiltunen
14.01.2020: Network part shall be ok if parameters.py used and communicates with the display.

This code is in its very beginning steps!

"""
from machine import SPI, Pin, reset, freq
import uasyncio as asyncio
import utime
import gc
from MQTT_AS import MQTTClient, config
import network
import ntptime
import webrepl
import MHZ19B as CO2
from XPT2046 import Touch
from ILI9341 import Display, color565
from XGLCD_FONT import XglcdFont
from TOUCH_KEYBOARD import TouchKeyboard
# For testing
# import esp


try:
    f = open('parameters.py', "r")
    from parameters import SSID1, SSID2, PASSWORD1, PASSWORD2, MQTT_SERVER, MQTT_PASSWORD, MQTT_USER, MQTT_PORT, \
        CLIENT_ID, TOPIC_ERRORS, CO2_SENSOR_RX_PIN, CO2_SENSOR_TX_PIN, CO2_SENSOR_UART, TFT_CS_PIN, TFT_DC_PIN, \
        TFT_TOUCH_MISO_PIN, TFT_TOUCH_CS_PIN, TFT_TOUCH_IRQ_PIN, TFT_TOUCH_MOSI_PIN, TFT_TOUCH_SCLK_PIN, TFT_CLK_PIN, \
        TFT_RST_PIN, TFT_MISO_PIN, TFT_MOSI_PIN, TFT_SPI, TOUCHSCREEN_SPI, WEBREPL_PASSWORD, NTPSERVER, DHCP_NAME
except OSError:  # open failed
    print("parameter.py-file missing! Can not continue!")
    raise

#  Globals
wifinet = None


def restart_and_reconnect():
    #  Last resort
    print("About to reboot in 20s... ctrl + c to break")
    utime.sleep(20)
    reset()


def resolve_date():
    (year, month, mdate, hour, minute, second, wday, yday) = utime.localtime()
    date = "%s.%s.%s time %s:%s:%s" % (mdate, month, year, "{:02d}".format(hour), "{:02d}".format(minute), "{:02d}".
                                       format(second))
    return date


async def error_reporting(error):
    # error message: date + time;uptime;devicename;ip;error;free mem
    errormessage = str(resolve_date()) + ";" + str(utime.ticks_ms()) + ";" \
        + str(CLIENT_ID) + ";" + str(network.WLAN(network.STA_IF).ifconfig()) + ";" + str(error) +\
        ";" + str(gc.mem_free())
    # await client.publish(TOPIC_ERRORS, str(errormessage), retain=False)


async def show_what_i_do():
    MQTTClient.DEBUG = False
    # esp.osdebug(all)
    # esp.osdebug(0)  # to UART0
    while True:
        print("CO2: %s" % co2sensor.co2_value)
        print("Average: %s" % co2sensor.co2_average)
        print("-------")
        await asyncio.sleep(1)


class ConnectWiFi:
    """ This class creates network object for WiFi-connection. SSID may be defined in the parameters.py or
    user may input a password, which is tried to WiFi APs within range. """

    def __init__(self):
        #  Check if we are already connected
        self.ip_address = None
        self.wifi_strenth = None
        self.timeset = False
        self.webrepl_started = False
        self.searh_list = []
        self.ssid_list = []
        if network.WLAN(network.STA_IF).config('essid') != '':
            display.row_by_row_text("Connected to network %s" % network.WLAN(network.STA_IF).config('essid'), 'white')
            self.use_ssid = network.WLAN(network.STA_IF).config('essid')
            display.row_by_row_text(('IP-address: %s' % network.WLAN(network.STA_IF).ifconfig()[0]), 'white')
            self.ip_address = network.WLAN(network.STA_IF).ifconfig()[0]
            display.row_by_row_text("WiFi-signal strength %s" % (network.WLAN(network.STA_IF).status('rssi')), 'white')
            self.wifi_strenth = network.WLAN(network.STA_IF).status('rssi')
            self.network_connected = True
            self.use_ssid = network.WLAN(network.STA_IF).config('essid')
            # resolve is essid in the predefined networks presented in parameters.py
            if self.use_ssid == SSID1:
                self.use_password = PASSWORD1
                self.predefined = True
            elif self.use_ssid == SSID2:
                self.use_password = PASSWORD2
                self.predefined = True
        else:
            # We are not connected, check if SSID1 or SSID2 is predefined
            if (SSID1 is not None) or (SSID2 is not None):
                self.predefined = True
            else:
                self.predefined = False
            self.password = None
            self.use_password = None    # Password may be from parameters.py or from user input
            self.use_ssid = None   # SSID to be used will be decided later even it is in the parameters.py
            self.network_connected = False
            self.search_and_connect_wifi_networks()

    def start_webrepl(self):
        if self.webrepl_started is False:
            if WEBREPL_PASSWORD is not None:
                try:
                    webrepl.start(password=WEBREPL_PASSWORD)
                    self.webrepl_started = True
                except OSError:
                    pass
            else:
                try:
                    webrepl.start()
                    self.webrepl_started = True
                except OSError as e:
                    print("WebREPL do not start. Error %s" % e)
                    display.row_by_row_text("WebREPL do not start. Error %s" % e, 'red')
                    return False

    def set_time(self):
        if self.timeset is False:
            try:
                ntptime.settime()
                self.timeset = True
            except OSError as e:
                print("No time from NTP server %s! Error %s" % (NTPSERVER, e))
                display.row_by_row_text("No time from NTP server %s! Error %s" % (NTPSERVER, e), 'red')
                self.timeset = True
                return False
            print("Time: %s " % str(utime.localtime(utime.time())))
            display.row_by_row_text("Time: %s " % str(utime.localtime(utime.time())), 'white')

    def search_and_connect_wifi_networks(self):
        # Begin with adapter reset
        network.WLAN(network.STA_IF).active(False)
        utime.sleep(1)
        network.WLAN(network.STA_IF).active(True)
        utime.sleep(2)
        if DHCP_NAME is not None:
            network.WLAN(network.STA_IF).config(dhcp_hostname=DHCP_NAME)
        if NTPSERVER is not None:
            ntptime.host = NTPSERVER
        display.row_by_row_text("Check what hotspots we see", 'white')
        try:
            # Generate list of WiFi hotspots in range
            self.ssid_list = network.WLAN(network.STA_IF).scan()
            utime.sleep(3)
        except self.ssid_list == []:
            print("No WiFi-networks within range!")
            display.row_by_row_text("No WiFi-networks within range!", 'red')
            utime.sleep(10)
        except OSError:
            return False

        if len(self.ssid_list) > 0:
            display.row_by_row_text("Found following hotspots:", 'white')
            for i in self.ssid_list:
                display.row_by_row_text(i[0].decode(), 'white')

        if self.predefined is True:
            #  Network to be connected is in the parameters.py. Check if SSID1 or SSID2 is in the list
            print("Checking if paramaters.py networks are in the list...")
            display.row_by_row_text("Checking predefined networks...", 'white')
            try:
                self.searh_list = [item for item in self.ssid_list if item[0].decode() == SSID1 or
                                   item[0].decode() == SSID2]
            except ValueError:
                # SSDI not found within signal range
                print("Parameters.py SSIDs not found in the signal range!")
                display.row_by_row_text("Parameters.py SSIDs not found in the signal range!", 'red')
                utime.sleep(10)
                return False
            # If both are found, select one which has highest stregth
            if len(self.searh_list) == 2:
                #  third from end of list is rssi
                if self.searh_list[0][-3] > self.searh_list[1][-3]:
                    self.use_ssid = self.searh_list[0][0].decode()
                    self.use_password = PASSWORD1
                    self.connect_to_network()
                else:
                    self.use_ssid = self.searh_list[1][0].decode()
                    self.use_password = PASSWORD2
                    self.connect_to_network()
            else:
                # only 1 in the list
                self.use_ssid = self.searh_list[0][0].decode()
                self.use_password = PASSWORD1
                self.connect_to_network()

        if self.predefined is False:
            #  Networks not defined in the parameters.py, let's try password to any WiFi order by signal strength
            #  Tries empty password too
            self.ssid_list.sort(key=lambda x: [x][-3])
            if len(self.ssid_list) == 1:
                self.use_ssid = self.ssid_list[0][0].decode()
                self.connect_to_network()
            elif len(self.ssid_list) > 1:
                z = 0
                while (network.WLAN(network.STA_IF).ifconfig()[0] == '0.0.0.0') and (z <= len(self.ssid_list)) and \
                        (self.network_connected is False):
                    self.use_ssid = self.ssid_list[z][0].decode()
                    self.connect_to_network()
                    z = +1

    def connect_to_network(self):
        #  We know which network we should connect to
        print("Connecting to AP %s ..." % self.use_ssid)
        display.row_by_row_text("Connecting to AP %s ..." % self.use_ssid, 'white')
        try:
            network.WLAN(network.STA_IF).connect(self.use_ssid, self.use_password)
            utime.sleep(5)
        except network.WLAN(network.STA_IF).ifconfig()[0] == '0.0.0.0':
            print("No IP address!")
            display.row_by_row_text("No IP address!", 'red')
            utime.sleep(10)
            return False
        except OSError:
            pass
        finally:
            if network.WLAN(network.STA_IF).ifconfig()[0] != '0.0.0.0':
                self.set_time()
                self.start_webrepl()
                display.row_by_row_text("Connected to network %s" % network.WLAN(network.STA_IF).config('essid'),
                                        'white')
                self.use_ssid = network.WLAN(network.STA_IF).config('essid')
                display.row_by_row_text(('IP-address: %s' % network.WLAN(network.STA_IF).ifconfig()[0]), 'white')
                self.ip_address = network.WLAN(network.STA_IF).ifconfig()[0]
                display.row_by_row_text("WiFi-signal strength %s" % (network.WLAN(network.STA_IF).status('rssi')),
                                        'white')
                self.wifi_strenth = network.WLAN(network.STA_IF).status('rssi')
                self.network_connected = True
                return True
            else:
                display.row_by_row_text("No network connection! Soft rebooting in 10s...", 'red')
                self.network_connected = False
                utime.sleep(10)
                reset()

    async def update_status_loop(self):
        while True:
            self.use_ssid = network.WLAN(network.STA_IF).config('essid')
            self.ip_address = network.WLAN(network.STA_IF).ifconfig()[0]
            self.wifi_strenth = network.WLAN(network.STA_IF).status('rssi')
            await asyncio.sleep(1)


class Mqtt:
    """ This class creates asynhronous mqtt-object """

    def __init__(self):
        # Asynchronous mqtt for updating outdoor mqtt status and sending errors to database
        config['server'] = MQTT_SERVER
        config['ssid'] = wifinet.use_ssid
        config['wifi_pw'] = wifinet.use_password
        config['user'] = MQTT_USER
        config['password'] = MQTT_PASSWORD
        config['port'] = MQTT_PORT
        config['client_id'] = CLIENT_ID
        config['subs_cb'] = self.update_mqtt_status
        config['connect_coro'] = self.mqtt_subscribe
        # Communication object
        self.client = MQTTClient(config)

    async def mqtt_up_loop(self):
        #  This loop just keeps the mqtt connection up
        await self.mqtt_subscribe()
        n = 0
        while True:
            await asyncio.sleep(5)
            print('mqtt-publish', n)
            await self.client.publish('result', '{}'.format(n), qos=1)
            n += 1

    async def mqtt_subscribe(self):
        await asyncio.sleep(1)
        # await client.subscribe(TOPIC_OUTDOOR, 0)

    def update_mqtt_status(self, topic, msg, retained):
        # print("Topic: %s, message %s" % (topic, msg))
        status = int(msg)
        if status == 1:
            print("daa")
        elif status == 0:
            print("kaa")


class TFTDisplay(object):
    #  Borrowed code from https://github.com/miketeachman/micropython-street-sense/blob/master/streetsense.py

    def __init__(self, touchspi, dispspi):

        self.colours = {'red': [255, 0, 0], 'green': [0, 255, 0], 'blue': [0, 0, 255], 'yellow': [255, 255, 0],
                        'fuschia': [255, 0, 255], 'aqua': [0, 255, 255], 'maroon': [128, 0, 0],
                        'darkgreen': [0, 128, 0], 'navy': [0, 0, 128], 'teal': [0, 128, 128], 'purple': [128, 0, 128],
                        'olive': [128, 128, 0], 'orange': [255, 128, 0], 'deep_pink': [255, 0, 128],
                        'charteuse': [128, 255, 0], 'spring_green': [0, 255, 128], 'indigo': [128, 0, 255],
                        'dodger_blue': [0, 128, 255], 'cyan': [128, 255, 255], 'pink': [255, 128, 255],
                        'light_yellow': [255, 255, 128], 'light_coral': [255, 128, 128], 'light_green': [128, 255, 128],
                        'white': [255, 255, 255]}

        self.xpt = Touch(spi=touchspi, cs=Pin(TFT_TOUCH_CS_PIN), int_pin=Pin(TFT_TOUCH_IRQ_PIN),
                         width=240, height=320, x_min=100, x_max=1962, y_min=100, y_max=1900,
                         int_handler=self.touchscreen_press)
        # Display
        self.display = Display(spi=dispspi, cs=Pin(TFT_CS_PIN), dc=Pin(TFT_DC_PIN), rst=Pin(TFT_RST_PIN),
                               width=320, height=240, rotation=90)

        self.wifinet = None
        # Default fonts
        self.unispace = XglcdFont('fonts/Unispace12x24.c', 12, 24)
        self.fixedfont = XglcdFont('fonts/FixedFont5x8.c', 5, 8, 32, 96)
        self.arcadepix = XglcdFont('fonts/ArcadePix9x11.c', 9, 11)
        self.color_r, self.color_g, self.color_b = self.colours['white']

        self.screens = [self.show_measurement_screen,
                        self.show_trends_screen(),
                        self.show_status_monitor_screen,
                        self.show_display_sleep_screen]
        # pin_screen = Pin(0, Pin.IN, Pin.PULL_UP)
        # pb_screen = Pushbutton(pin_screen)
        # pb_screen.press_func(self.next_screen)
        self.rownumber = 1
        self.rowheight = 10
        self.fontheight = 10
        self.maxrows = self.display.height / self.fontheight
        self.active_screen = 1
        self.next_screen = 0
        self.diag_count = 0
        self.screen_timeout = False
        self.keyboard = None

        # Test

        # loop = asyncio.get_event_loop()
        # loop.create_task(self.run_display())

    def touchscreen_press(self, x, y):
        # Set up Keyboard
        self.keyboard = TouchKeyboard(self.display, self.unispace)
        """Process touchscreen press events."""
        if self.keyboard.handle_keypress(x, y, debug=True) is True:
            self.keyboard.locked = True
            answer = self.keyboard.kb_text
            self.keyboard.show_message("Do you want to connect to network?", color565(0, 0, 255))
            self.keyboard.waiting = True
            self.keyboard.locked = False
            if answer == 'y':
                self.wifinet = ConnectWiFi()
            else:
                self.display.cleanup()

    def row_by_row_text(self, message, color):
        self.color_r, self.color_g, self.color_b = self.colours[color]
        self.fontheight = self.arcadepix.height
        self.rowheight = self.fontheight + 2  # 2 pixel space between rows
        self.display.draw_text(0, self.rowheight * self.rownumber, message, self.arcadepix,
                               color565(self.color_r, self.color_g, self.color_b))
        self.rownumber += 1
        if self.rownumber >= self.maxrows:
            utime.sleep(5)
            self.display.cleanup()
            self.rownumber = 1

    async def run_display(self):

        await self.show_welcome_screen()

        """ 

        # continually refresh the active screen

       while True:
            if self.next_screen != self.active_screen:
                self.active_screen = self.next_screen
                self.screen_timeout = False
                if modes[operating_mode].display == 'timeout':
                    self.timeout_timer.init(period=Display.SCREEN_TIMEOUT_IN_S * 1000,
                                            mode=Timer.ONE_SHOT,
                                            callback=self.screen_timeout_callback)
            elif self.screen_timeout is True:
                self.next_screen = len(self.screens) - 1

            # display the active screen
            await self.screens[self.active_screen]()
            await asyncio.sleep(Display.SCREEN_REFRESH_IN_S) """

    async def next_screen(self):
        self.next_screen = (self.active_screen + 1) % len(self.screens)

    def screen_timeout_callback(self, t):
        self.screen_timeout = True

    async def show_welcome_screen(self):
        self.row_by_row_text("Booting up", 'blue')

        await asyncio.sleep(9)
        self.display.cleanup()

    async def show_network_screen(self):
        pass

    async def show_measurement_screen(self):
        self.display.clear()
        self.display.draw_text(0, 90, "CO2: %s" % co2sensor.co2_value, self.unispace, color565(255, 128, 255))
        self.display.draw_text(0, 120, "CO2 average: %s" % co2sensor.co2_average,
                               self.unispace, color565(255, 128, 255))
        # display.draw_text(0, 150, 'Ticks CPU %s' % utime.ticks_cpu(), fixed_font, color565(255, 255, 255))

    async def show_trends_screen(self):
        pass

    async def show_status_monitor_screen(self):
        pass

    async def show_display_sleep_screen(self):
        pass

    async def show_decibel_screen(self):
        pass


# Kick in some speed, max 240000000, normal 160000000, min with WiFi 80000000
freq(240000000)


# Sensor and controller objects
co2sensor = CO2.MHZ19bCO2(CO2_SENSOR_RX_PIN, CO2_SENSOR_TX_PIN, CO2_SENSOR_UART)
touchscreenspi = SPI(TOUCHSCREEN_SPI)  # HSPI
touchscreenspi.init(baudrate=10000000, sck=Pin(TFT_TOUCH_SCLK_PIN), mosi=Pin(TFT_TOUCH_MOSI_PIN),
                    miso=Pin(TFT_TOUCH_MISO_PIN))
displayspi = SPI(TFT_SPI)  # VSPI
displayspi.init(baudrate=40000000, sck=Pin(TFT_CLK_PIN), mosi=Pin(TFT_MOSI_PIN), miso=Pin(TFT_MISO_PIN))

display = TFTDisplay(touchscreenspi, displayspi)


async def main():
    global wifinet

    # Start WiFi if already defined in the parameters.py
    if (SSID1 is not None) or (SSID2 is not None):
        wifinet = ConnectWiFi()
    else:
        # todo: make user input
        pass

    if wifinet.network_connected is True:
        asyncio.create_task(wifinet.update_status_loop())

    """ try:
        await client.connect()
    except OSError as ex:
        print("Error %s. Perhaps mqtt username or password is wrong or missing or broker down?" % ex)
        raise
    # asyncio.create_task(mqtt_up_loop()) """

    asyncio.create_task(co2sensor.read_co2_loop())
    asyncio.create_task(show_what_i_do())

    while True:
        await asyncio.sleep(10)

asyncio.run(main())
