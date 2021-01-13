""""

This script is used for airquality measurement. Display is ILI9341 2.8" TFT touch screen in the SPI bus,
CO2 device is MH-Z19 NDIR-sensor, particle sensor is PMS7003 and temperature/rh/pressure sensor BME280.

Boot.py does not setup network. If user wants to connect to the network and to the mqtt-server, that can be done
from the display either with predefined SSID name and password, or password for accessible networks.


Libraries:
1. MQTT_AS https://github.com/peterhinch/micropython-mqtt/blob/master/mqtt_as/mqtt_as.py
2. MHZ19B.py in this blob
3. ILI9341 display, touchscreen, fonts and keyboard https://github.com/rdagger/micropython-ili9341

!! DO NOT USE PyCharm to upload fonts or images to the ESP32! Use command ampy -p COMx directoryname instead!
   PyCharm can not handle directories in ESP32. For some reason it combines name of the directory and file to one file.
   
Very first draft

13.01.2020: Jari Hiltunen

"""
import machine
from machine import SPI, Pin, reset, freq
import uasyncio as asyncio
import utime
import gc
from MQTT_AS import MQTTClient, config
import network
import ntptime
import webrepl
import MHZ19B as CO2
import ILI9341 as TFTMODULE
from ILI9341 import color565
import TOUCH_KEYBOARD as KEYBOARD
import XGLCD_FONT as FONTS
import XPT2046 as TOUCHSREEN
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
fixed_font = FONTS.XglcdFont('fonts/FixedFont5x8.c', 5, 8)
wifinetwork = None


def set_time():
    try:
        ntptime.settime()
    except OSError as e:
        print("No time from NTP server! Error %s" % (NTPSERVER, e))
        restart_and_reconnect()
    print("Time: %s " % str(utime.localtime(utime.time())))


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

    def __init__(self, password):

        #  Check if we are already connected
        if network.WLAN(network.STA_IF).config('essid') != '':
            self.network_connected = True
            print("Connected to network %s" % network.WLAN(network.STA_IF).config('essid'))
            display.draw_text(0, 1, "Connected to network %s" % network.WLAN(network.STA_IF).config('essid'),
                              unispace, color565(255, 255, 255))
            # print('IP-address:', network.WLAN(network.STA_IF).ifconfig()[0])
            #display.draw_text(0, 30, "IP-address: %s" % network.WLAN(network.STA_IF).ifconfig()[0], unispace,
            #                       color565(255, 255, 255))
            print("WiFi-signal strength %s" % (network.WLAN(network.STA_IF).status('rssi')))
            display.draw_text(0, 60, "WiFi rssi: %s" % (network.WLAN(network.STA_IF).status('rssi')),
                                   unispace, color565(255, 0, 255))
        #  We are not connected
        else:
            self.network_connected = False
            self.searh_list = []
            self.ssid_list = []
            if password is not None:
                self.use_password = password
                self.use_ssid = None
                self.predefined = False
            elif (SSID1 is not None) or (SSID2 is not None):
                #  parameters.py defined networks
                self.predefined = True
                self.use_password = None
                self.use_ssid = None

    def start_webrepl(self):
        if WEBREPL_PASSWORD is not None:
            try:
                webrepl.start(password=WEBREPL_PASSWORD)
            except OSError:
                pass
        else:
            try:
                webrepl.start()
            except OSError as e:
                print("WebREPL do not start. Error %s" % e)
                raise Exception("WebREPL not installed! Install with REPL command import webrepl_setup")

    def search_wifi_networks(self):
        #  Search WiFi and try parameters SSID and passwords
        network.WLAN(network.STA_IF).active(False)
        utime.sleep(1)
        network.WLAN(network.STA_IF).active(True)
        utime.sleep(2)
        if DHCP_NAME is not None:
            network.WLAN(network.STA_IF).config(dhcp_hostname=DHCP_NAME)
        if NTPSERVER is not None:
            ntptime.host = NTPSERVER
        try:
            self.ssid_list = network.WLAN(network.STA_IF).scan()
            utime.sleep(3)
        except self.ssid_list == []:
            print("No WiFi-networks within range!")
            display.draw_text(0, 70, "No WiFi-networks within range!", unispace, color565(255, 0, 255))
            utime.sleep(10)
        except OSError:
            return False

        if self.predefined is True:
            #  Check if parameters.py SSID1 or SSID2 is in the list
            print("Checking if paramaters.py networks are in the list...")
            display.draw_text(0, 60, "Checking if paramaters.py networks are in the list...", unispace, color565(255, 0, 255))
            try:
                self.searh_list = [item for item in self.ssid_list if item[0].decode() == SSID1 or item[0].decode() == SSID2]
            except ValueError:
                # SSDI not found
                print("Parameters.py SSIDs not found!")
                display.draw_text(0, 70, "Can not find either SSID1 or SSID2. Please, select which network you want to"
                                  " connect", unispace, color565(255, 0, 255))
                utime.sleep(30)
            # If both are found, select one which has highest stregth
            if len(self.searh_list) == 2:
                #  third from end is rssi
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
        print("Connecting to AP %s" % self.use_ssid)
        display.draw_text(0, 80, "Connecting to AP %s" % self.use_ssid, unispace, color565(255, 0, 255))
        try:
            network.WLAN(network.STA_IF).connect(self.use_ssid, self.use_password)
            utime.sleep(5)
        except network.WLAN(network.STA_IF).ifconfig()[0] == '0.0.0.0':
            print("No IP address!")
            display.draw_text(0, 70, "No IP address!", unispace, color565(255, 0, 255))
            utime.sleep(10)
            return False
        except OSError:
            pass
        finally:
            if network.WLAN(network.STA_IF).ifconfig()[0] != '0.0.0.0':
                set_time()
                self.start_webrepl()
                print('IP-address:', network.WLAN(network.STA_IF).ifconfig()[0])
                display.draw_text(0, 90, "IP address: %s" % network.WLAN(network.STA_IF).ifconfig()[0],
                                  unispace, color565(255, 0, 255))
                print("WiFi-signal strength %s" % (network.WLAN(network.STA_IF).status('rssi')))
                display.draw_text(0, 100, "Signal strength %s" % (network.WLAN(network.STA_IF).status('rssi')),
                                  unispace, color565(255, 0, 255))
                self.network_connected = True
            else:
                print("No network connection!")
                display.draw_text(0, 70, "No network connection!", unispace, color565(255, 0, 255))
                utime.sleep(60)
                self.network_connected = True


class Mqtt:
    """ This class creates asynhronous mqtt-object """

    def __init__(self):
        # Asynchronous mqtt for updating outdoor mqtt status and sending errors to database
        config['server'] = MQTT_SERVER
        config['ssid'] = wifinetwork.use_ssid
        config['wifi_pw'] = wifinetwork.use_password
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

class UserMenu(object):

    def __init__(self, touchspi):
        # Set up display
        # self.display = TFTMODULE.Display(spi=dispspi, cs=Pin(TFT_CS_PIN), dc=Pin(TFT_DC_PIN), rst=Pin(TFT_RST_PIN),
        #                                 width=320, height=240, rotation=rotation)

        # Load font
        # self.unispace = FONTS.XglcdFont('fonts/Unispace12x24.c', 12, 24)
        self.keyboard = None
        self.keyboard_visible = False

        # Set up touchscreen
        self.xpt = TOUCHSREEN.Touch(spi=touchspi, cs=Pin(TFT_TOUCH_CS_PIN), int_pin=Pin(TFT_TOUCH_IRQ_PIN),
                                    int_handler=self.touchscreen_press)

    def lookup(self):
        display.clear()
        display.draw_text(0, 90, "CO2: %s" % co2sensor.co2_value, unispace, color565(255, 128, 255))
        display.draw_text(0, 120, "CO2 average: %s" % co2sensor.co2_average, unispace, color565(255, 128, 255))
        display.draw_text(0, 150, 'Ticks CPU %s' % utime.ticks_cpu(), fixed_font, color565(255, 255, 255))
        gc.collect()

    def touchscreen_press(self, x, y):
        # Set up Keyboard
        self.keyboard = KEYBOARD.TouchKeyboard(display, unispace)
        self.keyboard_visible = True
        """Process touchscreen press events."""
        if self.keyboard.handle_keypress(x, y, debug=False) is True:
            self.keyboard.locked = True
            pwd = self.keyboard.kb_text
            self.keyboard.show_message("Measuring...", color565(0, 0, 255))
            self.lookup()
            self.keyboard.waiting = True
            self.keyboard.locked = False


# Kick in some speed, max 240000000, normal 160000000, min with WiFi 80000000
freq(240000000)


# Sensor and controller objects
co2sensor = CO2.MHZ19bCO2(CO2_SENSOR_RX_PIN, CO2_SENSOR_TX_PIN, CO2_SENSOR_UART)
touchscreenspi = SPI(TOUCHSCREEN_SPI)  # HSPI
touchscreenspi.init(baudrate=10000000, sck=Pin(TFT_TOUCH_SCLK_PIN), mosi=Pin(TFT_TOUCH_MOSI_PIN),
                    miso=Pin(TFT_TOUCH_MISO_PIN))
displayspi = SPI(TFT_SPI)  # VSPI
displayspi.init(baudrate=40000000, sck=Pin(TFT_CLK_PIN), mosi=Pin(TFT_MOSI_PIN), miso=Pin(TFT_MISO_PIN))

# Display
display = TFTMODULE.Display(spi=displayspi, cs=Pin(TFT_CS_PIN), dc=Pin(TFT_DC_PIN), rst=Pin(TFT_RST_PIN),
                            width=320, height=240, rotation=270)
# Default font
unispace = FONTS.XglcdFont('fonts/Unispace12x24.c', 12, 24)
fixedfont = FONTS.XglcdFont('fonts/FixedFont5x8.c', 5, 8, 32, 96)


async def main():
    global wifinetwork
    # Network up
    wifinetwork = ConnectWiFi(password=None)

    #  Subroutine to make network connection
    UserMenu(touchscreenspi)

    """ try:
        await client.connect()
    except OSError as ex:
        print("Error %s. Perhaps mqtt username or password is wrong or missing or broker down?" % ex)
        raise
    # asyncio.create_task(mqtt_up_loop()) """

    asyncio.create_task(co2sensor.read_co2_loop())
    asyncio.create_task(show_what_i_do())

    while True:
        display.draw_text(0, 90, "CO2: %s" % co2sensor.co2_value, unispace, color565(255, 128, 255))
        display.draw_text(0, 120, "CO2 average: %s" % co2sensor.co2_average, unispace, color565(255, 128, 255))
        display.draw_text(0, 150, 'Ticks CPU %s' % utime.ticks_cpu(), fixed_font, color565(255, 255, 255))
        await asyncio.sleep(10)

asyncio.run(main())
