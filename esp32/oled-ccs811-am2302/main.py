"""
Scripti lukee sensoria ja näyttää kolme eri sivua tietoja sekä sensorista että ESP32:sta ja lähettää arvot
mqtt-brokerille.

Ulkoiset kirjastot:

SPI OLED näytölle: sh1160-kirjastoa, jonka voit ladata täältä https://github.com/robert-hh/SH1106

SPI kytkentä oletukset:

SSD1306       NodeMCU-32S(ESP32)
      GND ----> GND
      VCC ----> 3v3 (3.3V)
       D0 ----> GPIO 18 SCK (SPI Clock)
       D1 ----> GPIO 23 MOSI (sama kuin SDA)
      RES ----> GPIO 17 Reset
       DC ----> GPIO 16 Data/Command select
       CS ----> GPIO  5 Chip Select


CCS811 sensorille:   https://github.com/Notthemarsian/CCS811/blob/master/CCS811.py

I2C kytkentä oletukset:
    SCL = 22
    SDA = 21
    CCS811 muista kytkeä nWake -> GND!

Asynkroninen MQTT: https://github.com/peterhinch/micropython-mqtt/blob/master/mqtt_as/README.md


21.11.2020 Jari Hiltunen
22.11.2020 Lisätty DHT22 (AM2302) sensorin luku lämpötilalle ja kosteudelle
24.11.2020 Lisätty näytön kääntö, paikallisajan (dst) laskenta ja himmennys
29.11.2020 Lisätty sensorille lähetettävä tieto kosteudesta ja lämpötilasta, jotka parantavat tarkkuutta.

"""

from machine import I2C, SPI, Pin
import sh1106
import ccs811
import time
import uasyncio as asyncio
import utime
import esp32
from mqtt_as import MQTTClient
import network
import gc
from mqtt_as import config
import machine
import dht


# tuodaan parametrit tiedostosta parametrit.py
from parametrit import CLIENT_ID, MQTT_SERVERI, MQTT_PORTTI, MQTT_KAYTTAJA, \
    MQTT_SALASANA, SSID1, SALASANA1, SSID2, SALASANA2, AIHE_CO2, AIHE_TVOC, \
    DHT22_KOSTEUS_KORJAUSKERROIN, DHT22_LAMPO_KORJAUSKERROIN, DHT22_KOSTEUS, DHT22_LAMPO


kaytettava_salasana = None

if network.WLAN(network.STA_IF).config('essid') == SSID1:
    kaytettava_salasana = SALASANA1
elif network.WLAN(network.STA_IF).config('essid') == SSID2:
    kaytettava_salasana = SALASANA2

config['server'] = MQTT_SERVERI
config['ssid'] = network.WLAN(network.STA_IF).config('essid')
config['wifi_pw'] = kaytettava_salasana
config['user'] = MQTT_KAYTTAJA
config['password'] = MQTT_SALASANA
config['port'] = MQTT_PORTTI
config['client_id'] = CLIENT_ID
client = MQTTClient(config)
edellinen_mqtt_klo = utime.time()
aloitusaika = utime.time()
anturilukuvirheita = 0


def restart_and_reconnect():
    aika = ratkaise_aika()
    print('%s: Ongelmia. Boottaillaan 1s kuluttua.' % aika)
    time.sleep(1)
    machine.reset()
    # resetoidaan


class SPInaytonohjain:

    def __init__(self, res=17, dc=16, cs=5, sck=18, mosi=23, leveys=16, rivit=6, lpikselit=128, kpikselit=64):
        self.rivit = []
        self.nayttotekstit = []
        self.aika = 5  # oletusnäyttöaika
        self.rivi = 1
        """ Muodostetaan näytönohjaukseen tarvittavat objektit """
        # SPI-kytkennan pinnit
        self.res = Pin(res)  # reset
        self.dc = Pin(dc)  # data
        self.cs = Pin(cs)  # chip select
        # SPI-objektin luonti, sck = d0, mosi = SDA
        self.spi = SPI(2, baudrate=115200, sck=Pin(sck), mosi=Pin(mosi))
        # naytto-objektin luonti
        self.nayttoleveys = leveys  # merkkiä
        self.nayttorivit = rivit  # riviä
        self.pikselit_leveys = lpikselit  # pikseliä
        self.pikselit_korkeus = kpikselit
        self.naytto = sh1106.SH1106_SPI(self.pikselit_leveys, self.pikselit_korkeus, self.spi, self.dc,
                                        self.res, self.cs)
        self.naytto.poweron()
        self.naytto.init_display()
        self.kaanteinen = False

    async def pitka_teksti_nayttoon(self, teksti, aika, rivi=1):
        self.aika = aika
        self.rivi = rivi
        self.nayttotekstit.clear()
        self.rivit.clear()
        """ Teksti (str) ja aika (int) miten pitkään tekstiä näytetään """
        self.nayttotekstit = [teksti[y-self.nayttoleveys:y] for y in range(self.nayttoleveys,
                              len(teksti)+self.nayttoleveys, self.nayttoleveys)]
        for y in range(len(self.nayttotekstit)):
            self.rivit.append(self.nayttotekstit[y])
        if len(self.rivit) > self.nayttorivit:
            sivuja = len(self.nayttotekstit) // self.nayttorivit
        else:
            sivuja = 1
        if sivuja == 1:
            for z in range(0, len(self.rivit)):
                self.naytto.text(self.rivit[z], 0, self.rivi + z * 10, 1)

    async def teksti_riville(self, teksti, rivi, aika):
        self.aika = aika
        """ Teksti (str), rivit (int) ja aika (int) miten pitkään tekstiä näytetään """
        if len(teksti) > self.nayttoleveys:
            self.naytto.text('Rivi liian pitka', 0, 1 + rivi * 10, 1)
        elif len(teksti) <= self.nayttoleveys:
            self.naytto.text(teksti, 0, 1 + rivi * 10, 1)

    async def aktivoi_naytto(self):
        self.naytto.sleep(False)
        self.naytto.show()
        await asyncio.sleep(self.aika)
        self.naytto.sleep(True)
        self.naytto.init_display()

    async def kontrasti(self, kontrasti=255):
        if kontrasti > 1 or kontrasti < 255:
            self.naytto.contrast(kontrasti)

    async def kaanteinen_vari(self, kaanteinen=False):
        self.kaanteinen = kaanteinen
        self.naytto.invert(kaanteinen)

    async def kaanna_180_astetta(self, kaanna=False):
        self.naytto.rotate(kaanna)

    async def piirra_kehys(self):
        if self.kaanteinen is False:
            self.naytto.framebuf.rect(1, 1, self.pikselit_leveys-1, self.pikselit_korkeus-1, 0xffff)
        else:
            self.naytto.framebuf.rect(1, 1, self.pikselit_leveys - 1, self.pikselit_korkeus - 1, 0x0000)

    async def piirra_alleviivaus(self, rivi, leveys):
        rivikorkeus = self.pikselit_korkeus / self.nayttorivit
        alkux = 1
        alkuy = 8 + (int(rivikorkeus * rivi))
        merkkileveys = int(8 * leveys)
        if self.kaanteinen is False:
            self.naytto.framebuf.hline(alkux, alkuy, merkkileveys, 0xffff)
        else:
            self.naytto.framebuf.hline(alkux, alkuy, merkkileveys, 0x0000)

    async def resetoi_naytto(self):
        self.naytto.reset()


class KaasuSensori:

    def __init__(self, i2cvayla=0, scl=22, sda=21, taajuus=400000, osoite=90):
        self.i2c = I2C(i2cvayla, scl=Pin(scl), sda=Pin(sda), freq=taajuus)
        self.laiteosoite = osoite
        self.sensori = ccs811.CCS811(self.i2c)
        self.eCO2 = 0
        self.tVOC = 0
        self.eCO2_keskiarvo = 0
        self.eCO2_arvoja = 0
        self.tVOC_keskiarvo = 0
        self.tVOC_arvoja = 0
        self.luettu_aika = utime.time()

    async def lue_arvot(self):
        while True:
            if self.sensori.data_ready():
                self.eCO2 = self.sensori.eCO2
                self.tVOC = self.sensori.tVOC
                self.luettu_aika = utime.time()
            await asyncio.sleep_ms(1000)

    async def laheta_lampo_ja_kosteus_korjaus(self, lampoin, kosteusin):
        if (float(lampoin) > -40) and (float(lampoin) < 150) and (float(kosteusin) > 0) and (float(kosteusin) < 101):
            self.sensori.put_envdata(float(kosteusin), float(lampoin))


class LampojaKosteus:

    def __init__(self, pinni=4, lukuvali=2):
        self.pinni = pinni
        self.lukuvali = lukuvali
        self.lampo = None
        self.kosteus = None
        self.anturi = dht.DHT22(Pin(self.pinni))
        self.lampo_keskiarvo = 0
        self.kosteus_keskiarvo = 0

    async def lue_arvot(self):
        global anturilukuvirheita
        while True:
            try:
                self.anturi.measure()
            except OSError as e:
                print("Anturilukuvirhe %s", e)
                self.lampo = None
                self.kosteus = None
                anturilukuvirheita += 1
                if anturilukuvirheita > 50:
                    restart_and_reconnect()
            if (self.anturi.temperature() > -40) and (self.anturi.temperature() < 150):
                self.lampo = '{:.1f}'.format(self.anturi.temperature() * DHT22_LAMPO_KORJAUSKERROIN)
            if (self.anturi.humidity() > 0) and (self.anturi.humidity() < 101):
                self.kosteus = '{:.1f}'.format(self.anturi.humidity() * DHT22_KOSTEUS_KORJAUSKERROIN)
            await asyncio.sleep(self.lukuvali)


def ratkaise_aika():
    (vuosi, kuukausi, kkpaiva, tunti, minuutti, sekunti, viikonpva, vuosipaiva) = utime.localtime()
    """ Simppeli DST """
    kesa_maalis = utime.mktime((vuosi, 3, (14 - (int(5 * vuosi / 4 + 1)) % 7), 1, 0, 0, 0, 0, 0))
    talvi_marras = utime.mktime((vuosi, 10, (7 - (int(5 * vuosi / 4 + 1)) % 7), 1, 0, 0, 0, 0, 0))
    if utime.mktime(utime.localtime()) < kesa_maalis:
        dst = utime.localtime(utime.mktime(utime.localtime()) + 10800)
    elif utime.mktime(utime.localtime()) < talvi_marras:
        dst = utime.localtime(utime.mktime(utime.localtime()) + 7200)
    else:
        dst = utime.localtime(utime.mktime(utime.localtime()) + 7200)
    (vuosi, kuukausi, kkpaiva, tunti, minuutti, sekunti, viikonpva, vuosipaiva) = dst
    paiva = "%s.%s.%s" % (kkpaiva, kuukausi, vuosi)
    kello = "%s:%s:%s" % ("{:02d}".format(tunti), "{:02d}".format(minuutti), "{:02d}".format(sekunti))
    return paiva, kello


naytin = SPInaytonohjain()
kaasusensori = KaasuSensori()
tempjarh = LampojaKosteus()


async def kerro_tilannetta():
    while True:
        # print("RSSI %s" % network.WLAN(network.STA_IF).status('rssi'), end=",")
        if tempjarh.lampo is not None:
            print('Lampo: %s C' % tempjarh.lampo)
        if tempjarh.kosteus is not None:
            print('Kosteus: %s %%' % tempjarh.kosteus)
        await asyncio.sleep(1)


async def laske_keskiarvot():
    eco2_keskiarvot = []
    tvoc_keskiarvot = []
    lampo_keskiarvot = []
    kosteus_keskiarvot = []

    while True:
        if kaasusensori.eCO2 > 0:
            eco2_keskiarvot.append(kaasusensori.eCO2)
            kaasusensori.eCO2_keskiarvo = (sum(eco2_keskiarvot) / len(eco2_keskiarvot))
            kaasusensori.eCO2_arvoja = len(eco2_keskiarvot)
            if len(eco2_keskiarvot) > 100:
                eco2_keskiarvot.clear()
        if kaasusensori.tVOC > 0:
            tvoc_keskiarvot.append(kaasusensori.tVOC)
            kaasusensori.tVOC_keskiarvo = (sum(tvoc_keskiarvot) / len(tvoc_keskiarvot))
            kaasusensori.tVOC_arvoja = len(tvoc_keskiarvot)
            if len(tvoc_keskiarvot) > 100:
                tvoc_keskiarvot.clear()
        if tempjarh.lampo is not None:
            lampo_keskiarvot.append(float(tempjarh.lampo))
            tempjarh.lampo_keskiarvo = sum(lampo_keskiarvot) / len(lampo_keskiarvot)
            if len(lampo_keskiarvot) > 100:
                lampo_keskiarvot.clear()
        if tempjarh.kosteus is not None:
            kosteus_keskiarvot.append(float(tempjarh.kosteus))
            tempjarh.kosteus_keskiarvo = sum(kosteus_keskiarvot) / len(kosteus_keskiarvot)
            if len(kosteus_keskiarvot) > 100:
                kosteus_keskiarvot.clear()
        await asyncio.sleep(1)


async def sivu_1():
    await naytin.teksti_riville("PVM:  %s" % ratkaise_aika()[0], 0, 5)
    await naytin.teksti_riville("KLO:  %s" % ratkaise_aika()[1], 1, 5)
    await naytin.piirra_alleviivaus(1, 20)
    await naytin.teksti_riville("eCO2: %s ppm" % kaasusensori.eCO2, 2, 5)
    #  Raja-arvot ovat yleisiä CO2:n haitallisuuden arvoja
    if kaasusensori.eCO2 > 1200:
        await naytin.kaanteinen_vari(True)
    else:
        await naytin.kaanteinen_vari(False)
    await naytin.teksti_riville("tVOC: %s ppb" % kaasusensori.tVOC, 3, 5)
    if kaasusensori.tVOC > 100:
        await naytin.kaanteinen_vari(True)
    else:
        await naytin.kaanteinen_vari(False)
    if tempjarh.lampo is not None:
        await naytin.teksti_riville("Temp: %s C" % tempjarh.lampo, 4, 5)
    if tempjarh.kosteus is not None:
        await naytin.teksti_riville("Rh:   %s %%" % tempjarh.kosteus, 5, 5)
    await naytin.kaanna_180_astetta(True)
    if (ratkaise_aika()[1] > '20:00:00') and (ratkaise_aika()[1] < '08:00:00'):
        await naytin.kontrasti(2)
    else:
        await naytin.kontrasti(100)
    await naytin.aktivoi_naytto()
    # await naytin.piirra_alleviivaus(3, 7)
    await asyncio.sleep_ms(100)


async def sivu_2():
    await naytin.teksti_riville("KESKIARVOT", 0, 5)
    await naytin.piirra_alleviivaus(0, 10)
    if kaasusensori.eCO2_keskiarvo > 1200:
        await naytin.kaanteinen_vari(True)
    if kaasusensori.tVOC_keskiarvo > 100:
        await naytin.kaanteinen_vari(True)
    await naytin.teksti_riville("eCO2:{:0.1f} ppm ".format(kaasusensori.eCO2_keskiarvo), 2, 5)
    await naytin.teksti_riville("tVOC:{:0.1f} ppb".format(kaasusensori.tVOC_keskiarvo), 3, 5)
    await naytin.teksti_riville("Temp:{:0.1f} C".format(tempjarh.lampo_keskiarvo), 4, 5)
    await naytin.teksti_riville("Rh  :{:0.1f} %".format(tempjarh.kosteus_keskiarvo), 5, 5)
    await naytin.kaanna_180_astetta(True)
    if (ratkaise_aika()[1] > '20:00:00') and (ratkaise_aika()[1] < '08:00:00'):
        await naytin.kontrasti(2)
    else:
        await naytin.kontrasti(100)
    await naytin.aktivoi_naytto()
    await asyncio.sleep_ms(100)


async def sivu_3():
    """ Statussivulla näytetään yleisiä tietoja """
    await naytin.teksti_riville("STATUS", 0, 5)
    await naytin.piirra_alleviivaus(0, 6)
    await naytin.teksti_riville("Up s.: %s" % (utime.time() - aloitusaika), 1, 5)
    await naytin.teksti_riville("AP: %s" % network.WLAN(network.STA_IF).config('essid'), 2, 5)
    await naytin.teksti_riville("rssi: %s" % network.WLAN(network.STA_IF).status('rssi'), 3, 5)
    await naytin.teksti_riville("Memfree: %s" % gc.mem_free(), 4, 5)
    await naytin.teksti_riville("Hall: %s" % esp32.hall_sensor(), 5, 5)
    await naytin.kaanna_180_astetta(True)
    #  Himmennetään näyttöä yöksi
    if (ratkaise_aika()[1] > '20:00:00') and (ratkaise_aika()[1] < '08:00:00'):
        await naytin.kontrasti(2)
    else:
        await naytin.kontrasti(100)
    await naytin.aktivoi_naytto()
    await asyncio.sleep_ms(100)


async def mqtt_raportoi():
    """ Raportoidaan tiedot mqtt-brokerille ja asetetaan samalla ccs811-sensorille uudet lämpö ja kosteus """
    global edellinen_mqtt_klo
    n = 0
    while True:
        await asyncio.sleep(5)
        # print('mqtt-publish', n)
        await client.publish('result', '{}'.format(n), qos=1)
        n += 1
        if (kaasusensori.eCO2_keskiarvo > 0) and (kaasusensori.tVOC_keskiarvo > 0) and \
                (tempjarh.lampo is not None) and (tempjarh.kosteus is not None) and \
                (utime.time() - edellinen_mqtt_klo) > 60:
            try:
                await client.publish(AIHE_CO2, str(kaasusensori.eCO2_keskiarvo), retain=False, qos=0)
                await client.publish(AIHE_TVOC, str(kaasusensori.tVOC_keskiarvo), retain=False, qos=0)
                await client.publish(DHT22_LAMPO, str(tempjarh.lampo), retain=False, qos=0)
                await client.publish(DHT22_KOSTEUS, str(tempjarh.kosteus), retain=False, qos=0)
                await kaasusensori.laheta_lampo_ja_kosteus_korjaus(tempjarh.kosteus, tempjarh.lampo)
                edellinen_mqtt_klo = utime.time()
            except OSError as e:
                await naytin.kaanteinen_vari(True)
                await naytin.pitka_teksti_nayttoon("Virhe %s:" % e, 5)
                await naytin.aktivoi_naytto()


async def main():
    MQTTClient.DEBUG = False
    await client.connect()
    #  Aktivoi seuraava rivi jos haluat nähdä taustatoimintoja
    # asyncio.create_task(kerro_tilannetta())
    asyncio.create_task(kaasusensori.lue_arvot())
    asyncio.create_task(tempjarh.lue_arvot())
    asyncio.create_task(laske_keskiarvot())
    asyncio.create_task(mqtt_raportoi())

    while True:
        await sivu_1()
        await sivu_2()
        await sivu_3()
        gc.collect()

asyncio.run(main())
