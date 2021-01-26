""""
This script is used for airquality measurement. Display is ILI9341 2.8" TFT touch screen in the SPI bus,
CO2 device is MH-Z19 NDIR-sensor, particle sensor is PMS7003 and temperature/rh/pressure sensor BME280.

Draft code. Removed comments and refactorer variable names to save memory!

Updated: 26.01.2020: Jari Hiltunen
"""
from machine import SPI, I2C, Pin, freq, reset_cause
import uasyncio as asyncio
import utime
import gc
from MQTT_AS import MQTTClient, config
import network
import ntptime
import webrepl
from XPT2046 import Touch
from ILI9341 import Display, color565
from XGLCD_FONT import XglcdFont
from AQI import AQI
import PMS7003_AS as PARTICLES
import MHZ19B_AS as CO2
import BME280_float as BmE
import json


try:
    f = open('parameters.py', "r")
    from parameters import CO2_SEN_RX_PIN, CO2_SEN_TX_PIN, CO2_SEN_UART, TFT_CS_PIN, TFT_DC_PIN, \
        TS_MISO_PIN, TS_CS_PIN, TS_IRQ_PIN, TS_MOSI_PIN, TS_SCLK_PIN, TFT_CLK_PIN, \
        TFT_RST_PIN, TFT_MISO_PIN, TFT_MOSI_PIN, TFT_SPI, TS_SPI, \
        P_SEN_UART, P_SEN_TX, P_SEN_RX, I2C_SCL_PIN, I2C_SDA_PIN
    f.close()
except OSError:  # open failed
    print("parameter.py-file missing! Can not continue!")
    raise

try:
    f = open('runtimeconfig.json', 'r')
    with open('runtimeconfig.json') as config_file:
        data = json.load(config_file)
        f.close()
        SSID1 = data['SSID1']
        SSID2 = data['SSID2']
        PASSWORD1 = data['PASSWORD1']
        PASSWORD2 = data['PASSWORD2']
        MQTT_SERVER = data['MQTT_SERVER']
        MQTT_PASSWORD = data['MQTT_PASSWORD']
        MQTT_USER = data['MQTT_USER']
        MQTT_PORT = data['MQTT_PORT']
        MQTT_INTERVAL = data['MQTT_INTERVAL']
        CLIENT_ID = data['CLIENT_ID']
        TOPIC_ERRORS = data['TOPIC_ERRORS']
        WEBREPL_PASSWORD = data['WEBREPL_PASSWORD']
        NTPSERVER = data['NTPSERVER']
        DHCP_NAME = data['DHCP_NAME']
        START_WEBREPL = data['START_WEBREPL']
        START_NETWORK = data['START_NETWORK']
        START_MQTT = data['START_MQTT']
        SCREEN_UPDATE_INTERVAL = data['SCREEN_UPDATE_INTERVAL']
        DEBUG_SCREEN_ACTIVE = data['DEBUG_SCREEN_ACTIVE']
        SCREEN_TIMEOUT = data['SCREEN_TIMEOUT']
        TOPIC_TEMP = data['TOPIC_TEMP']
        TOPIC_RH = data['TOPIC_RH']
        TOPIC_PRESSURE = data['TOPIC_PRESSURE']
        TOPIC_AIRQUALITY = data['TOPIC_AIRQUALITY']
        TOPIC_CO2 = data['TOPIC_CO2']
        TOPIC_PM1_0 = data['TOPIC_PM1_0']
        TOPIC_PM1_0_ATM = data['TOPIC_PM1_0_ATM']
        TOPIC_PM2_5 = data['TOPIC_PM2_5']
        TOPIC_PM2_5_ATM = data['TOPIC_PM2_5_ATM']
        TOPIC_PM10_0 = data['TOPIC_PM10_0']
        TOPIC_PM10_0_ATM = data['TOPIC_PM10_0_ATM']
        TOPIC_PCNT_0_3 = data['TOPIC_PCNT_0_3']
        TOPIC_PCNT_0_5 = data['TOPIC_PCNT_0_5']
        TOPIC_PCNT_1_0 = data['TOPIC_PCNT_1_0']
        TOPIC_PCNT_2_5 = data['TOPIC_PCNT_2_5']
        TOPIC_PCNT_5_0 = data['TOPIC_PCNT_5_0']
        TOPIC_PCNT_10_0 = data['TOPIC_PCNT_10_0']
        CO2_ALM_THOLD = data['CO2_ALARM_TRESHOLD']
        AQ_THOLD = data['AIRQUALIY_TRESHOLD']
        TEMP_THOLD = data['TEMP_TRESHOLD']
        TEMP_CORRECTION = data['TEMP_CORRECTION']
        RH_THOLD = data['RH_TRESHOLD']
        RH_CORRECTION = data['RH_CORRECTION']
        P_THOLD = data['PRESSURE_TRESHOLD']
        PRESSURE_CORRECTION = data['PRESSURE_CORRECTION']

except OSError:
    print("Runtime parameters missing. Can not continue!")
    utime.sleep(30)
    raise


def resolve_date():
    (year, month, mdate, hour, minute, second, wday, yday) = utime.localtime()
    weekdays = ['Ma', 'Ti', 'Ke', 'To', 'Pe', 'La', 'Su']
    summer_march = utime.mktime((year, 3, (14 - (int(5 * year / 4 + 1)) % 7), 1, 0, 0, 0, 0, 0))
    winter_december = utime.mktime((year, 10, (7 - (int(5 * year / 4 + 1)) % 7), 1, 0, 0, 0, 0, 0))
    if utime.mktime(utime.localtime()) < summer_march:
        dst = utime.localtime(utime.mktime(utime.localtime()) + 7200)
    elif utime.mktime(utime.localtime()) < winter_december:
        dst = utime.localtime(utime.mktime(utime.localtime()) + 7200)
    else:
        dst = utime.localtime(utime.mktime(utime.localtime()) + 10800)
    (year, month, mdate, hour, minute, second, wday, yday) = dst
    day = "%s.%s.%s" % (mdate, month, year)
    time = "%s:%s:%s" % ("{:02d}".format(hour), "{:02d}".format(minute), "{:02d}".format(second))
    return day, time, weekdays[wday]


class ConnectWiFi(object):

    def __init__(self):
        self.net_ok = False
        self.password = None
        self.u_pwd = None
        self.use_ssid = None
        self.ip_a = None
        self.strength = None
        self.timeset = False
        self.s_comp = False
        self.webrepl_started = False
        self.searh_list = []
        self.ssid_list = []
        self.mqttclient = None
        self.con_att_fail = 0
        self.startup_time = None

    async def network_update_loop(self):
        # TODO: add While True
        if START_NETWORK == 1:
            await self.c_net()
            if self.net_ok is False:
                await self.s_nets()
                if (self.s_comp is True) and (self.con_att_fail <= 20):
                    await self.connect_to_network()
                    if self.con_att_fail > 20:
                        # Give up
                        return False
        if self.net_ok is True:
            if self.timeset is False:
                await self.set_time()
            if self.webrepl_started is False:
                await self.start_webrepl()
        await asyncio.sleep(5)

    async def c_net(self):
        if network.WLAN(network.STA_IF).config('essid') != '':
            #  Already connected
            self.use_ssid = network.WLAN(network.STA_IF).config('essid')
            self.ip_a = network.WLAN(network.STA_IF).ifconfig()[0]
            self.strength = network.WLAN(network.STA_IF).status('rssi')
            self.net_ok = True
            self.use_ssid = network.WLAN(network.STA_IF).config('essid')
            # resolve is essid in the predefined networks presented in config
            if self.use_ssid == SSID1:
                self.u_pwd = PASSWORD1
            elif self.use_ssid == SSID2:
                self.u_pwd = PASSWORD2
        else:
            self.password = None
            self.u_pwd = None
            self.use_ssid = None
            self.net_ok = False

    async def start_webrepl(self):
        if (self.webrepl_started is False) and (START_WEBREPL == 1):
            if WEBREPL_PASSWORD is not None:
                try:
                    webrepl.start(password=WEBREPL_PASSWORD)
                    self.webrepl_started = True
                except OSError:
                    self.webrepl_started = False
                    pass
            else:
                try:
                    webrepl.start()
                    self.webrepl_started = True
                except OSError:
                    self.webrepl_started = False
                    return False
        await asyncio.sleep(5)

    async def set_time(self):
        if NTPSERVER is not None:
            ntptime.host = NTPSERVER
        if self.timeset is False:
            try:
                ntptime.settime()
                self.timeset = True
                self.startup_time = utime.time()
            except OSError as e:
                self.timeset = False
                return False
        await asyncio.sleep(5)

    async def s_nets(self):
        network.WLAN(network.STA_IF).active(False)
        await asyncio.sleep(2)
        network.WLAN(network.STA_IF).active(True)
        await asyncio.sleep(3)
        try:
            self.ssid_list = network.WLAN(network.STA_IF).scan()
            await asyncio.sleep(5)
        except self.ssid_list == []:
            # No hotspots
            return False
        except OSError:
            return False
        try:
            self.searh_list = [item for item in self.ssid_list if item[0].decode() == SSID1 or
                               item[0].decode() == SSID2]
        except ValueError:
            return False
        if len(self.searh_list) == 2:
            if self.searh_list[0][-3] > self.searh_list[1][-3]:
                self.use_ssid = self.searh_list[0][0].decode()
                self.u_pwd = PASSWORD1
                self.s_comp = True
            else:
                self.use_ssid = self.searh_list[1][0].decode()
                self.u_pwd = PASSWORD2
                self.s_comp = True
        else:
            self.use_ssid = self.searh_list[0][0].decode()
            self.u_pwd = PASSWORD1
            self.s_comp = True

    async def connect_to_network(self):
        if DHCP_NAME is not None:
            network.WLAN(network.STA_IF).config(dhcp_hostname=DHCP_NAME)
        try:
            network.WLAN(network.STA_IF).connect(self.use_ssid, self.u_pwd)
            await asyncio.sleep(10)
        except network.WLAN(network.STA_IF).ifconfig()[0] == '0.0.0.0':
            self.net_ok = False
            self.con_att_fail += 1
            return False
        except OSError:
            pass
        finally:
            if network.WLAN(network.STA_IF).ifconfig()[0] != '0.0.0.0':
                self.use_ssid = network.WLAN(network.STA_IF).config('essid')
                self.ip_a = network.WLAN(network.STA_IF).ifconfig()[0]
                self.strength = network.WLAN(network.STA_IF).status('rssi')
                self.net_ok = True
            else:
                self.net_ok = False
                self.con_att_fail += 1
        await asyncio.sleep(1)

    def mqtt_init(self):
        config['server'] = MQTT_SERVER
        config['ssid'] = self.use_ssid
        config['wifi_pw'] = self.u_pwd
        config['user'] = MQTT_USER
        config['password'] = MQTT_PASSWORD
        config['port'] = MQTT_PORT
        config['client_id'] = CLIENT_ID
        config['subs_cb'] = self.update_mqtt_status
        config['connect_coro'] = self.mqtt_subscribe
        # Communication object
        self.mqttclient = MQTTClient(config)

    async def mqtt_up_loop(self):
        #  This loop just keeps the mqtt connection up
        await self.mqtt_subscribe()
        n = 0
        while True:
            await asyncio.sleep(5)
            print('mqtt-publish', n)
            await self.mqttclient.publish('result', '{}'.format(n), qos=1)
            n += 1

    async def mqtt_subscribe(self):
        await asyncio.sleep(1)
        # await self.mqttclient.subscribe(TOPIC_OUTDOOR, 0)

    def update_mqtt_status(self, topic, msg, retained):
        pass
        """ Subscribe mqtt topics for correction multipliers and such. As an example, if
        temperature measurement is linearly wrong +0,8C, send substraction via mqtt-topic. If measurement is 
        not linearly wrong, pass range + correction to the topics.
        # print("Topic: %s, message %s" % (topic, msg))
        Example:
        if topic == '/device_id/temp/correction/':
            correction = float(msg)
            return correction
        """


class TFTDisplay(object):

    def __init__(self, touchspi, dispspi):

        # Display - some digitizers may be rotated 270 degrees!
        self.d = Display(spi=dispspi, cs=Pin(TFT_CS_PIN), dc=Pin(TFT_DC_PIN), rst=Pin(TFT_RST_PIN),
                         width=320, height=240, rotation=90)

        # Default fonts
        self.unispace = XglcdFont('fonts/Unispace12x24.c', 12, 24)
        self.arcadepix = XglcdFont('fonts/ArcadePix9x11.c', 9, 11)
        self.a_font = self.unispace

        self.cols = {'red': color565(255, 0, 0), 'green': color565(0, 255, 0), 'blue': color565(0, 0, 255),
                     'yellow': color565(255, 255, 0), 'fuschia': color565(255, 0, 255),
                     'aqua': color565(0, 255, 255), 'maroon': color565(128, 0, 0),
                     'darkgreen': color565(0, 128, 0), 'navy': color565(0, 0, 128),
                     'teal': color565(0, 128, 128), 'purple': color565(128, 0, 128),
                     'olive': color565(128, 128, 0), 'orange': color565(255, 128, 0),
                     'deep_pink': color565(255, 0, 128), 'charteuse': color565(128, 255, 0),
                     'spring_green': color565(0, 255, 128), 'indigo': color565(128, 0, 255),
                     'dodger_blue': color565(0, 128, 255), 'cyan': color565(128, 255, 255),
                     'pink': color565(255, 128, 255), 'light_yellow': color565(255, 255, 128),
                     'light_coral': color565(255, 128, 128), 'light_green': color565(128, 255, 128),
                     'white': color565(255, 255, 255), 'black': color565(0, 0, 0)}

        self.c_fnts = 'white'
        self.col_bckg = 'light_green'

        # Touchscreen
        self.xpt = Touch(spi=touchspi, cs=Pin(TS_CS_PIN), int_pin=Pin(TS_IRQ_PIN),
                         width=240, height=320, x_min=100, x_max=1962, y_min=100, y_max=1900)
        self.xpt.int_handler = self.first_touch
        self.t_tched = False
        self.scr_actv_time = None
        self.r_num = 1
        self.r_h = 10
        self.f_h = 10
        self.f_w = 10
        self.max_r = self.d.height / self.f_h
        self.indent_p = 12
        self.scr_tout = SCREEN_TIMEOUT
        self.d_all_ok = True
        self.scr_upd_ival = SCREEN_UPDATE_INTERVAL
        self.d_scr_active = False
        self.rw_col = None
        self.rows = None
        self.dtl_scr_sel = None

    def first_touch(self, x, y):
        gc.collect()
        self.t_tched = True

    async def rot_scr(self):
        self.d_scr_active = True
        r, r_c = await self.particle_screen()
        await self.show_screen(r, r_c)
        r, r_c = await self.status_monitor()
        await self.show_screen(r, r_c)
        self.d_scr_active = False
        self.t_tched = False

    async def disp_loop(self):

        # NOTE: Loop is started in the main()

        while True:

            if self.t_tched is True:
                if self.d_scr_active is False:
                    await self.rot_scr()
                elif (self.d_scr_active is True) and \
                        ((utime.time() - self.scr_actv_time) > self.scr_tout):
                    # Timeout
                    self.d_scr_active = False
                    self.t_tched = False
            else:
                r, r_c = await self.upd_welcome()
                await self.show_screen(r, r_c)
                gc.collect()

    async def show_screen(self, rows, row_colours):
        r1 = "Airquality 0.02"
        r1_c = 'white'
        r2 = "."
        r2_c = 'white'
        r3 = "Wait"
        r3_c = 'white'
        r4 = "For"
        r4_c = 'white'
        r5 = "Values"
        r5_c = 'white'
        r6 = "."
        r6_c = 'white'
        r7 = "Wait"
        r7_c = 'white'

        # strip too long lines!

        if rows is not None:
            if len(rows) == 7:
                r1, r2, r3, r4, r5, r6, r7 = rows
            if len(row_colours) == 7:
                r1_c, r2_c, r3_c, r4_c, r5_c, r6_c, r7_c = row_colours
        if self.d_all_ok is True:
            await self.ok_bckg()
        else:
            await self.error_bckg()
        self.a_font = self.unispace
        self.f_h = self.a_font.height
        self.r_h = self.f_h + 2  # 2 pixel space between rows
        self.d.draw_text(self.indent_p, 25, r1, self.a_font, self.cols[r1_c], self.cols[self.col_bckg])
        self.d.draw_text(self.indent_p, 25 + self.r_h, r2, self.a_font, self.cols[r2_c], self.cols[self.col_bckg])
        self.d.draw_text(self.indent_p, 25 + self.r_h * 2, r3, self.a_font, self.cols[r3_c], self.cols[self.col_bckg])
        self.d.draw_text(self.indent_p, 25 + self.r_h * 3, r4, self.a_font, self.cols[r4_c], self.cols[self.col_bckg])
        self.d.draw_text(self.indent_p, 25 + self.r_h * 4, r5, self.a_font, self.cols[r5_c], self.cols[self.col_bckg])
        self.d.draw_text(self.indent_p, 25 + self.r_h * 5, r6, self.a_font, self.cols[r6_c], self.cols[self.col_bckg])
        self.d.draw_text(self.indent_p, 25 + self.r_h * 6, r7, self.a_font, self.cols[r7_c], self.cols[self.col_bckg])
        await asyncio.sleep(self.scr_upd_ival)

    async def ok_bckg(self):
        self.d.fill_rectangle(0, 0, self.d.width, self.d.height, self.cols['yellow'])
        # TODO: replace excact values to display size values
        self.d.fill_rectangle(10, 10, 300, 220, self.cols['light_green'])
        self.col_bckg = 'light_green'

    async def error_bckg(self):
        self.d.fill_rectangle(0, 0, self.d.width, self.d.height, self.cols['red'])
        self.d.fill_rectangle(10, 10, 300, 220, self.cols['light_green'])
        self.col_bckg = 'light_green'

    @staticmethod
    async def upd_welcome():
        r1 = "%s %s %s" % (resolve_date()[2], resolve_date()[0], resolve_date()[1])
        r1_c = 'black'
        if co2s.co2_value is None:
            r2 = "CO2: waiting..."
            r2_c = 'yellow'
        elif co2s.co2_average is None:
            r2 = "CO2 average counting..."
            r2_c = 'yellow'
        else:
            r2 = "CO2: %s ppm (%s)" % ("{:.1f}".format(co2s.co2_value), "{:.1f}".format(co2s.co2_average))
            if (co2s.co2_average > CO2_ALM_THOLD) or (co2s.co2_value > CO2_ALM_THOLD):
                r2_c = 'red'
            else:
                r2_c = 'blue'
        if aq.aqinndex is None:
            r3 = "AirQuality not ready"
            r3_c = 'yellow'
        else:
            r3 = "Air Quality Index: %s" % ("{:.1f}".format(aq.aqinndex))
            if aq.aqinndex > AQ_THOLD:
                r3_c = 'red'
            else:
                r3_c = 'blue'
        if bmes.values[0] is None:
            r4 = "Waiting values..."
            r4_c = 'yellow'
        else:
            r4 = "Temp: %s" % bmes.values[0]
            if float(bmes.values[0][:-1]) > TEMP_THOLD:
                r4_c = 'red'
            else:
                r4_c = 'blue'
        if bmes.values[2] is None:
            r5 = "Waiting values..."
            r5_c = 'yellow'
        else:
            r5 = "Humidity: %s" % bmes.values[2]
            if float(bmes.values[2][:-1]) > RH_THOLD:
                r5_c = 'red'
            else:
                r5_c = 'blue'
        if bmes.values[1] is None:
            r6 = "Waiting values..."
            r6_c = 'yellow'
        else:
            r6 = "Pressure: %s ATM" % bmes.values[1]
            if float(bmes.values[1][:-3]) > P_THOLD:
                r6_c = 'red'
            else:
                r6_c = 'blue'
        r7 = "Touch screen for details"
        r7_c = 'white'
        rows = r1, r2, r3, r4, r5, r6, r7
        row_colours = r1_c, r2_c, r3_c, r4_c, r5_c, r6_c, r7_c
        return rows, row_colours

    @staticmethod
    async def particle_screen():
        if pms.pms_dictionary is not None:
            r1 = "1. Concentration ug/m3:"
            r1_c = 'blue'
            if (pms.pms_dictionary['PM1_0'] is not None) and (pms.pms_dictionary['PM1_0_ATM'] is not None) and \
                    (pms.pms_dictionary['PM2_5'] is not None) and (pms.pms_dictionary['PM2_5_ATM'] is not None):
                r2 = " PM1:%s (%s) PM2.5:%s (%s)" % (pms.pms_dictionary['PM1_0'], pms.pms_dictionary['PM1_0_ATM'],
                                                     pms.pms_dictionary['PM2_5'], pms.pms_dictionary['PM2_5_ATM'])
                r2_c = 'black'
            else:
                r2 = " Waiting"
                r2_c = 'yellow'
            if (pms.pms_dictionary['PM10_0'] is not None) and (pms.pms_dictionary['PM10_0_ATM'] is not None):
                r3 = " PM10: %s (ATM: %s)" % (pms.pms_dictionary['PM10_0'], pms.pms_dictionary['PM10_0_ATM'])
                r3_c = 'black'

            else:
                r3 = "Waiting"
                r3_c = 'yellow'
            r4 = "2. Particle count/1L/um:"
            r4_c = 'blue'
            if (pms.pms_dictionary['PCNT_0_3'] is not None) and (pms.pms_dictionary['PCNT_0_5'] is not None):
                r5 = " %s < 0.3 & %s <0.5 " % (pms.pms_dictionary['PCNT_0_3'], pms.pms_dictionary['PCNT_0_5'])
                r5_c = 'navy'
            else:
                r5 = " Waiting"
                r5_c = 'yellow'
            if (pms.pms_dictionary['PCNT_1_0'] is not None) and (pms.pms_dictionary['PCNT_2_5'] is not None):
                r6 = " %s < 1.0 & %s < 2.5" % (pms.pms_dictionary['PCNT_1_0'], pms.pms_dictionary['PCNT_2_5'])
                r6_c = 'navy'
            else:
                r6 = "Waiting"
                r6_c = 'yellow'
            if (pms.pms_dictionary['PCNT_5_0'] is not None) and (pms.pms_dictionary['PCNT_10_0'] is not None):
                r7 = " %s < 5.0 & %s < 10.0" % (pms.pms_dictionary['PCNT_5_0'], pms.pms_dictionary['PCNT_10_0'])
                r7_c = 'navy'
            else:
                r7 = " Waiting"
                r7_c = 'yellow'
            rows = r1, r2, r3, r4, r5, r6, r7
            row_colours = r1_c, r2_c, r3_c, r4_c, r5_c, r6_c, r7_c
            return rows, row_colours
        else:
            return None

    async def show_network_screen(self):
        pass

    async def show_trends_screen(self):
        pass

    @staticmethod
    async def status_monitor():
        row1 = "Memory free: %s" % gc.mem_free()
        row1_colour = 'black'
        row2 = "Uptime: %s" % (utime.time() - net.startup_time)
        row2_colour = 'blue'
        row3 = "WiFi IP: %s" % net.ip_a
        row3_colour = 'blue'
        row4 = "WiFi Strength: %s" % net.strength
        row4_colour = 'blue'
        row5 = "MHZ19B CRC errors: %s " % co2s.crc_errors
        row5_colour = 'white'
        row6 = "MHZ19B Range errors: %s" % co2s.range_errors
        row6_colour = 'white'
        row7 = "PMS7003 version %s" % pms.pms_dictionary['VERSION']
        row7_colour = 'white'
        rows = row1, row2, row3, row4, row5, row6, row7
        row_colours = row1_colour, row2_colour, row3_colour, row4_colour, row5_colour, row6_colour, row7_colour
        return rows, row_colours

    async def show_display_sleep_screen(self):
        pass

    async def show_network_setup_screen(self):
        pass


class AirQuality(object):

    def __init__(self, pmssensor):
        self.aqinndex = None
        self.pms = pmssensor
        self.upd_ival = 5

    async def upd_aq_loop(self):
        while True:
            if self.pms.pms_dictionary is not None:
                if (self.pms.pms_dictionary['PM2_5_ATM'] != 0) and (self.pms.pms_dictionary['PM10_0_ATM'] != 0):
                    self.aqinndex = (AQI.aqi(self.pms.pms_dictionary['PM2_5_ATM'],
                                             self.pms.pms_dictionary['PM10_0_ATM']))
            await asyncio.sleep(self.upd_ival)


async def upd_status_loop():
    while True:
        # For network
        if net.net_ok is True:
            net.use_ssid = network.WLAN(network.STA_IF).config('essid')
            net.ip_a = network.WLAN(network.STA_IF).ifconfig()[0]
            net.wifi_strenth = network.WLAN(network.STA_IF).status('rssi')

        # For sensors tresholds, background change
        if co2s.co2_average is not None:
            if co2s.co2_average > CO2_ALM_THOLD:
                display.d_all_ok = False
            elif co2s.co2_average <= CO2_ALM_THOLD:
                display.d_all_ok = True
        if aq.aqinndex is not None:
            if aq.aqinndex > AQ_THOLD:
                display.d_all_ok = False
            elif aq.aqinndex <= AQ_THOLD:
                display.d_all_ok = True
        if bmes.values[0] is not None:
            if float(bmes.values[0][:-1]) > TEMP_THOLD:
                display.d_all_ok = False
            else:
                display.d_all_ok = True
        if bmes.values[2] is not None:
            if float(bmes.values[2][:-1]) > RH_THOLD:
                display.d_all_ok = False
            else:
                display.d_all_ok = True
        if bmes.values[1] is not None:
            if float(bmes.values[1][:-3]) > P_THOLD:
                display.d_all_ok = False
            else:
                display.d_all_ok = True
        else:
            display.d_all_ok = True
        await asyncio.sleep(display.scr_upd_ival - 2)


async def show_what_i_do():
    # Output is REPL
    MQTTClient.DEBUG = False

    while True:
        # print("PMS dictionary: %s" % pms.pms_dictionary)
        # print("Air quality index: %s " % airquality.aqinndex)
        # print("CO2: %s" % co2sensor.co2_value)
        # print("Average: %s" % co2sensor.co2_average)
        # print("WiFi Connected %s" % wifinet.network_connected)
        # print("WiFi failed connects %s" % wifinet.connect_attemps_failed)
        print("Memory free: %s" % gc.mem_free())
        print("Toucscreen pressed: %s" % display.t_tched)
        print("Details screen active: %s" % display.d_scr_active)
        print("-------")
        await asyncio.sleep(1)


# Kick in some speed, max 240000000, normal 160000000, min with WiFi 80000000
# freq(240000000)

net = ConnectWiFi()

# Sensor and controller objects
# Particle sensor
pms = PARTICLES.PSensorPMS7003(uart=P_SEN_UART, rxpin=P_SEN_RX, txpin=P_SEN_TX)
aq = AirQuality(pms)
# CO2 sensor
co2s = CO2.MHZ19bCO2(uart=CO2_SEN_UART, rxpin=CO2_SEN_RX_PIN, txpin=CO2_SEN_TX_PIN)
i2c = I2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN))
bmes = BmE.BME280(i2c=i2c)

#  If you use UART2, you have to delete object and re-create it after power on boot!
if reset_cause() == 1:
    del co2s
    utime.sleep(5)   # 2 is not enough!
    co2s = CO2.MHZ19bCO2(uart=CO2_SEN_UART, rxpin=CO2_SEN_RX_PIN, txpin=CO2_SEN_TX_PIN)
t_spi = SPI(TS_SPI)  # HSPI
t_spi.init(baudrate=1100000, sck=Pin(TS_SCLK_PIN), mosi=Pin(TS_MOSI_PIN),
           miso=Pin(TS_MISO_PIN))
d_spi = SPI(TFT_SPI)  # VSPI - baudrate 40 - 90 MHz appears to be working, screen update still slow
d_spi.init(baudrate=40000000, sck=Pin(TFT_CLK_PIN), mosi=Pin(TFT_MOSI_PIN), miso=Pin(TFT_MISO_PIN))
display = TFTDisplay(t_spi, d_spi)


async def main():
    loop = asyncio.get_event_loop()
    loop.create_task(net.network_update_loop())
    loop.create_task(pms.read_async_loop())
    loop.create_task(co2s.read_co2_loop())
    loop.create_task(aq.upd_aq_loop())
    loop.create_task(upd_status_loop())
    if DEBUG_SCREEN_ACTIVE == 1:
        loop.create_task(show_what_i_do())
    loop.create_task(display.disp_loop())
    loop.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
