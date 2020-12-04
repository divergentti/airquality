"""

Esimerkki

"""


import uasyncio as asyncio
import MHZ19BCO2 as co2
import utime
import machine


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


sensori = co2.MHZ19bCO2()


async def kerro_tilannetta():
    while True:
        print("CO2: %s luettu %s" % (sensori.co2_arvo, sensori.arvo_luettu_klo))
        print("Keskiarvo: ", sensori.co2_keskiarvo)
        print("Sensorin käyntiaika: ", (utime.time() - sensori.sensori_aktivoitu_klo))
        await asyncio.sleep(1)


async def main():
    #  ESP32 oletusnopeus on 160 MHZ, lasketaan CPU lämmöntuoton vuoksi
    machine.freq(80000000)
    # Taustalle menevät prosessit
    asyncio.create_task(sensori.lue_co2_looppi())
    asyncio.create_task(kerro_tilannetta())

    while True:
        await asyncio.sleep(5)

asyncio.run(main())
