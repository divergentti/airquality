""" boot.py 2.0

This boot version support two different SSID names and passwords. The same SSID and password will be used
in the main.py for mqtt_as.py, which takes care of seldom WiFi and mqtt-broker dropouts.

1) Set WebRepl with import web_repl.
2) Remember to add parameters to the parameters.py file!

16.10.2020 Jari Hiltunen

"""

import utime
import machine
import network
import time
import ntptime
import webrepl
from time import sleep

#  0 = power on, 6 = hard reset, 1 = WDT reset, 5 = DEEP_SLEEP reset, 4 soft reset
print("Previous boot reason %s" % machine.reset_cause())

try:
    f = open('parameters.py', "r")
    from parameters import SSID1, SSID2, PASSWORD1, PASSWORD2, WEBREPL_PASSWORD, NTPSERVER, DHCP_NAME
except OSError:  # open failed
    print("parameter.py-file missing! Can not continue!")
    raise


def can_not_connect():
    print("No connection. Rebooting...")
    sleep(1)
    machine.reset()


def set_time():
    try:
        ntptime.settime()
    except OSError as e:
        print("No time from NTP server! Error %s" % (NTPSERVER, e))
        can_not_connect()
    print("Time: %s " % str(utime.localtime(utime.time())))


def start_webrepl():
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


wificlient_if = network.WLAN(network.STA_IF)


#  Connection is up due to reboot reason 4, 6
if wificlient_if.config('essid') != '':
    print("Connected to network %s" % network.WLAN(network.STA_IF).config('essid'))
    print('IP-address:', network.WLAN(network.STA_IF).ifconfig()[0])
    print("WiFi-signal strength %s" % (network.WLAN(network.STA_IF).status('rssi')))
    set_time()
    start_webrepl()
else:
    #  Search WiFi
    searh_list = []
    ssid_list = []
    use_password = ""
    use_ssid = ""
    wificlient_if = network.WLAN(network.STA_IF)
    wificlient_if.active(False)
    time.sleep(1)
    wificlient_if.active(True)
    time.sleep(2)
    if DHCP_NAME is not None:
        wificlient_if.config(dhcp_hostname=DHCP_NAME)
    if NTPSERVER is not None:
        ntptime.host = NTPSERVER
    try:
        ssid_list = wificlient_if.scan()
        time.sleep(3)
    except KeyboardInterrupt:
        raise
    except ssid_list == []:
        print("No WiFi-networks!")
        can_not_connect()
    except OSError:
        can_not_connect()
        #  Check if SSID1 or SSID2 is in the list
    try:
        searh_list = [item for item in ssid_list if item[0].decode() == SSID1 or item[0].decode() == SSID2]
    except ValueError:
        # SSDI not found
        print("Can not find either SSID1 or SSID2!")
        can_not_connect()
    # If both are found, select one which has highest stregth
    if len(searh_list) == 2:
        #  third from end is rssi
        if searh_list[0][-3] > searh_list[1][-3]:
            use_ssid = searh_list[0][0].decode()
            use_password = PASSWORD1
        else:
            use_ssid = searh_list[1][0].decode()
            use_password = PASSWORD2
    else:
        # only 1 in the list
        use_ssid = searh_list[0][0].decode()
        use_password = PASSWORD1
    # machine.freq(240000000)

    print("Connecting to AP %s" % use_ssid)
    try:
        wificlient_if.connect(use_ssid, use_password)
        time.sleep(5)
    except wificlient_if.ifconfig()[0] == '0.0.0.0':
        print("No IP address!")
        can_not_connect()
    except OSError:
        can_not_connect()
    finally:
        if wificlient_if.ifconfig()[0] != '0.0.0.0':
            set_time()
            start_webrepl()
            print('IP-address:', wificlient_if.ifconfig()[0])
            print("WiFi-signal strength %s" % (wificlient_if.status('rssi')))
        else:
            can_not_connect()
