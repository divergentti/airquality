""" This class is for asynchronous WiFi connection.

In: minimal SSID1 and PASSWORD1, you may provide 2 SSIDs and passwords.
- WebREPL start. If you have installled WebREPL with import webrepl and you want to remotely use REPL
- WebREPL password.
- Network time server name for NTPTIME
- DHCP name for the adapter. Keep unique in your LAN.

Operation:
- Add asynchronous loop to your async main(): example loop.create_task(net.net_upd_loop())
- search available hotspots in range
- if provided ssid1 or ssid2 is in range, pick highest strength hotspot
- for MQTT_AS.py provide information in which AP we are connected to with which password
- If handshake with the WiFi fails > 20 times, returns false
- If ntptime is success, set this class startuptime to time()

DO NOT TRANSFER FILES TO ESP32 PyCharm Windows! It does not handle directories correctly (target dir use /, not \)!
-  use ampy -p COM4 put drivers\WIFICONN_AS.py drivers/WIFICONN_AS.py

29.01.2020: Jari Hiltunen
"""
import gc
import uasyncio as asyncio
import network
import ntptime
import webrepl
from utime import time
gc.collect()


class ConnectWiFi(object):

    def __init__(self, ssid1, password1, ssid2=None, password2=None, ntpserver=None, dhcpname=None,
                 startwebrepl=False, webreplpwd=None):
        self.ssid1 = ssid1
        self.pw1 = password1
        self.ssid2 = ssid2
        self.pw2 = password2
        self.ntps = ntpserver
        self.dhcpn = dhcpname
        self.starwbr = startwebrepl
        self.webrplpwd = webreplpwd
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
        self.con_att_fail = 0
        self.con_att_max = 20
        self.startup_time = None

    async def net_upd_loop(self):
        while True:
            if self.net_ok is False:
                await self.c_net()
                if self.net_ok is False:
                    await self.s_nets()
                    if (self.s_comp is True) and (self.con_att_fail <= self.con_att_max):
                        await self.connect_to_network()
                        if self.con_att_fail > self.con_att_max:
                            print("WiFi connection tried %s times, giving up" % self.con_att_fail)
                            return False
            if self.net_ok is True:
                if self.timeset is False:
                    await self.set_time()
                if (self.starwbr is True) and (self.webrepl_started is False):
                    await self.start_webrepl()
                    gc.collect()
            await asyncio.sleep(5)

    async def c_net(self):
        if network.WLAN(network.STA_IF).config('essid') != '':
            #  Already connected
            self.use_ssid = network.WLAN(network.STA_IF).config('essid')
            self.ip_a = network.WLAN(network.STA_IF).ifconfig()[0]
            self.strength = network.WLAN(network.STA_IF).status('rssi')
            self.net_ok = True
            self.use_ssid = network.WLAN(network.STA_IF).config('essid')
            # resolve is connected essid in the class init variables
            if self.use_ssid == self.ssid1:
                self.u_pwd = self.pw1
            elif self.use_ssid == self.ssid2:
                self.u_pwd = self.pw2
        else:
            self.password = None
            self.u_pwd = None
            self.use_ssid = None
            self.net_ok = False

    async def start_webrepl(self):
        if (self.webrepl_started is False) and (self.starwbr is True):
            if self.webrplpwd is not None:
                try:
                    webrepl.start(password=self.webrplpwd)
                    self.webrepl_started = True
                except OSError as e:
                    print("Error %s", e)
                    self.webrepl_started = False
                    pass
            else:
                try:
                    webrepl.start()
                    self.webrepl_started = True
                except OSError as e:
                    print("Error %s", e)
                    self.webrepl_started = False
                    return False
        await asyncio.sleep(5)

    async def set_time(self):
        if self.ntps is not None:
            ntptime.host = self.ntps
        if self.timeset is False:
            try:
                ntptime.settime()
                self.timeset = True
                self.startup_time = time()
            except OSError as e:
                print("Error %s", e)
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
            # No hotspots in range
            print("No hotspots in range!")
            return False
        except OSError as e:
            print("Error %s", e)
            return False
        try:
            if (self.ssid1 is not None) and (self.ssid2 is not None):
                self.searh_list = [item for item in self.ssid_list if item[0].decode() == self.ssid1 or
                                   item[0].decode() == self.ssid2]
            else:
                self.searh_list = [item for item in self.ssid_list if item[0].decode() == self.ssid1]
        except ValueError as e:
            print("SSID not found in range! %s" % e)
            return False
        if len(self.searh_list) == 2:
            if self.searh_list[0][-3] > self.searh_list[1][-3]:
                self.use_ssid = self.searh_list[0][0].decode()
                self.u_pwd = self.pw1
                self.s_comp = True
            else:
                self.use_ssid = self.searh_list[1][0].decode()
                self.u_pwd = self.pw2
                self.s_comp = True
        else:
            self.use_ssid = self.searh_list[0][0].decode()
            self.u_pwd = self.pw1
            self.s_comp = True

    async def connect_to_network(self):
        if self.dhcpn is not None:
            network.WLAN(network.STA_IF).config(dhcp_hostname=self.dhcpn)
        try:
            network.WLAN(network.STA_IF).connect(self.use_ssid, self.u_pwd)
            await asyncio.sleep(10)
        except network.WLAN(network.STA_IF).ifconfig()[0] == '0.0.0.0':
            self.net_ok = False
            self.con_att_fail += 1
            print("Connection attempt failed %s times" % self.con_att_fail)
            return False
        except OSError as e:
            print("Error %s", e)
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
                print("Connection attempt failed %s times" % self.con_att_fail)
        await asyncio.sleep(1)
