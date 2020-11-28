""" Boottiversio 2.0

Parametrit tuodaan parametrit.py-tidesosta. Vähintään tarvitaan SSID1 ja SALASANA1 joilla kerrotaan
mihin Wifi-AP halutaan yhdistää. Mikäli WebREPL:ä halutaan käyttää, tulee ensimmäisellä kerralla
käynnistää komento import webrepl_setup, joka luo tiedoston webrepl_cfg.py laitteen juureen.
Komennoilla import os, os.rename('vanha_tiedosto', 'uusi_tiedosto') tai os.remove('tiedostonimi')
voit käsitellä laitteen tiedostoja joko WebREPL tai konsoliportin kautta.

Tässä boottiversiossa skannataan aluksi kaikki WiFi AP:t ja niiden voimakkuus dBm. Tästä listasta valitaan
se WiFi AP jolla on korkein rssi ja yritetään autentikoida AP:hen. Mikäli autentikointi ei onnistu, kokeillaan
seuraavaa listassa olevaa. Lista on tässä scriptissä SSID1 ja SSID2 ja niille vastaava salasanat SALASANA1 ja 2.

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
print("Edellisen bootin syy %s" % machine.reset_cause())

try:
    from parametrit import SSID1, SSID2, SALASANA1, SALASANA2, WEBREPL_SALASANA, NTPPALVELIN, DHCP_NIMI
except ImportError as e:
    print("Tuontivirhe %s", e)
    if (SSID1 is not None) and (SALASANA1 is not None):
        SSID2 = None
        SALASANA2 = None
        WEBREPL_SALASANA = None
        NTPPALVELIN = None
        DHCP_NIMI = None
    else:
        print("Vaaditaan minim SSID1 ja SALASANA!")
        raise


def ei_voida_yhdistaa():
    print("Yhteys ei onnistu. Bootataan 1 s. kuluttua")
    sleep(1)
    machine.reset()


def aseta_aika():
    try:
        ntptime.settime()
    except OSError as e:
        print("NTP-palvelimelta %s ei saatu aikaa! Virhe %s" % (NTPPALVELIN, e))
        ei_voida_yhdistaa()
    print("Aika: %s " % str(utime.localtime(utime.time())))


def kaynnista_webrepl():
    if WEBREPL_SALASANA is not None:
        try:
            webrepl.start(password=WEBREPL_SALASANA)
        except OSError:
            pass
    else:
        try:
            webrepl.start()
        except OSError as e:
            print("WebREPL ei kaynnisty. Virhe %s" % e)
            raise Exception("WebREPL ei ole asenettu! Suorita import webrepl_setup")


wificlient_if = network.WLAN(network.STA_IF)


#  Ollaan jo yhteydessä 1, 2 tai 4 resetin vuoksi
if wificlient_if.config('essid') != '':
    print("Yhteydessä verkkoon %s" % network.WLAN(network.STA_IF).config('essid'))
    print('Laitteen IP-osoite:', network.WLAN(network.STA_IF).ifconfig()[0])
    print("WiFi-verkon signaalitaso %s" % (network.WLAN(network.STA_IF).status('rssi')))
    aseta_aika()
    kaynnista_webrepl()
else:
    etsi_lista = []
    ssid_lista = []
    kaytettava_salasana = ""
    kaytettava_ssid = ""
    wificlient_if = network.WLAN(network.STA_IF)
    wificlient_if.active(False)
    time.sleep(1)
    wificlient_if.active(True)
    time.sleep(2)
    if DHCP_NIMI is not None:
        wificlient_if.config(dhcp_hostname=DHCP_NIMI)
    if NTPPALVELIN is not None:
        ntptime.host = NTPPALVELIN
    try:
        ssid_lista = wificlient_if.scan()
        time.sleep(3)
    except KeyboardInterrupt:
        raise
    except ssid_lista == []:
        print("WiFi-verkkoja ei löydy!")
        ei_voida_yhdistaa()
    except OSError:
        ei_voida_yhdistaa()
        #  Katsotaan löytyvätkö SSID1 ja SSID2 listalta
    try:
        etsi_lista = [item for item in ssid_lista if item[0].decode() == SSID1 or item[0].decode() == SSID2]
    except ValueError:
        # SSDI ei löydy
        print("Etsittyä WiFi-verkkoja ei löydy!")
        ei_voida_yhdistaa()
    # Mikäli listan pituus on 2, silloin löytyi molemmat ja valitaan voimakkain, muuten valitaan vain se joka löytyi
    if len(etsi_lista) == 2:
        #  kolmas lopusta on signaalinvoimakkuus rssi
        if etsi_lista[0][-3] > etsi_lista[1][-3]:
            kaytettava_ssid = etsi_lista[0][0].decode()
            kaytettava_salasana = SALASANA1
        else:
            kaytettava_ssid = etsi_lista[1][0].decode()
            kaytettava_salasana = SALASANA2
    else:
        # vain yksi listalla
        kaytettava_ssid = etsi_lista[0][0].decode()
        kaytettava_salasana = SALASANA1
    # machine.freq(240000000)

    print("Yhdistetään verkkoon %s" % kaytettava_ssid)
    try:
        wificlient_if.connect(kaytettava_ssid, kaytettava_salasana)
        time.sleep(5)
    except wificlient_if.ifconfig()[0] == '0.0.0.0':
        print("Ei saada ip-osoitetta!")
        ei_voida_yhdistaa()
    except OSError:
        ei_voida_yhdistaa()
    finally:
        if wificlient_if.ifconfig()[0] != '0.0.0.0':
            aseta_aika()
            kaynnista_webrepl()
            print('Laitteen IP-osoite:', wificlient_if.ifconfig()[0])
            print("WiFi-verkon signaalitaso %s" % (wificlient_if.status('rssi')))
        else:
            ei_voida_yhdistaa()

