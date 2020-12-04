"""

MH-Z19 sensorin datasheetti https://www.winsen-sensor.com/d/files/MH-Z19B.pdf

"""


import uasyncio as asyncio
import MHZ19BCO2 as co2
import SH1106 as oled
import utime
import machine
from machine import Pin, I2C


class I2Cnaytonohjain:

    def __init__(self, scl=18, sda=23, leveys=16, rivit=6, lpikselit=128, kpikselit=64):
        self.rivit = []
        self.nayttotekstit = []
        self.aika = 5  # oletusnäyttöaika
        self.rivi = 1
        """ Muodostetaan näytönohjaukseen tarvittavat objektit """
        self.i2c = I2C(1, scl=Pin(scl), sda=Pin(sda), freq=400000)
        # naytto-objektin luonti
        self.nayttoleveys = leveys  # merkkiä
        self.nayttorivit = rivit  # riviä
        self.pikselit_leveys = lpikselit  # pikseliä
        self.pikselit_korkeus = kpikselit
        self.naytto = oled.SH1106_I2C(self.pikselit_leveys, self.pikselit_korkeus, self.i2c)
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


co2sensori = co2.MHZ19bCO2()
naytin = I2Cnaytonohjain()


async def kerro_tilannetta():
    while True:
        print("CO2: %s luettu %s" % (co2sensori.co2_arvo, co2sensori.arvo_luettu_klo))
        print("Keskiarvo: ", co2sensori.co2_keskiarvo)
        print("Sensorin käyntiaika: ", (utime.time() - co2sensori.sensori_aktivoitu_klo))
        await asyncio.sleep(1)


async def sivu_1():
    await naytin.teksti_riville("PVM:  %s" % ratkaise_aika()[0], 0, 5)
    await naytin.teksti_riville("KLO:  %s" % ratkaise_aika()[1], 1, 5)
    await naytin.piirra_alleviivaus(1, 20)
    await naytin.teksti_riville("CO2: %s ppm" % co2sensori.co2_arvo, 2, 5)
    #  Raja-arvot ovat yleisiä CO2:n haitallisuuden arvoja
    if co2sensori.co2_arvo > 1200:
        await naytin.kaanteinen_vari(True)
    else:
        await naytin.kaanteinen_vari(False)
    await naytin.kaanna_180_astetta(True)
    if (ratkaise_aika()[1] > '20:00:00') and (ratkaise_aika()[1] < '08:00:00'):
        await naytin.kontrasti(2)
    else:
        await naytin.kontrasti(100)
    await naytin.aktivoi_naytto()
    # await naytin.piirra_alleviivaus(3, 7)
    await asyncio.sleep_ms(100)


async def main():
    #  ESP32 oletusnopeus on 160 MHZ, lasketaan CPU lämmöntuoton vuoksi
    machine.freq(80000000)
    # Taustalle menevät prosessit
    asyncio.create_task(co2sensori.lue_co2_looppi())
    asyncio.create_task(kerro_tilannetta())

    while True:
        await sivu_1()
        await asyncio.sleep(5)

asyncio.run(main())
