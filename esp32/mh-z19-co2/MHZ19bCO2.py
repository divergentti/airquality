"""

MH-Z19 sensorin datasheetti https://www.winsen-sensor.com/d/files/MH-Z19B.pdf

Oletuksena on käyttää 0 - 5000 ppm sensoria. Tarkkuus ± (50ppm+5%)
Toimintajännite: 4.5 ~ 5.5 V DC, keskimääräinen kulutus < 20mA, maksimi 150mA
Toimintalämpötila -10 ~ 50 °C ja kosteus 0~ 90% RH.
Signaalin lähtö 3.3V sopiva. Vasteaika T90 < 120 s.
Sensorin elinikä > 5 vuotta.

Sensoria voi lukea myös PWM-muodossa, mutta tässä käytetään sarjamuotoista liikennettä (UART).

Komennot:
- 0x86 = lue CO2 konsentraatio, 8 bittiä:
  - Lähetyksessä: 0 = 0xFF (starttibitti), 1 = varattu, 2 = komento 0x86, 3-7 = 0x00, 8 = tarkistussumma 0x79
  - Vastaanototssa: 0 = 0xFF, 1 = komento 0x86, 2 = konsentraatio high-tavu, 3 = konsentraatio low-tavu, 4-7=0x00, 8 crc
  CO2-konsentraatio on tavu 2 (HIGH) * 256 + tavu 3 (LOW)
  Esimerkki: konvertoi hexa 02 desimaaliksi 2, hexa 20 desimaaliksi 32, jolloin 2 x 256 + 32 = 554 ppm CO2

- 0x87 = kalibroi nollapiste
  - 0 = 0xFF, 1 = 0x01 varattu, 2 = komento 0x87, 3-7 = 0x00, 8 = 0x78 crc
  Aseta sensori ulkoilmaan, jossa CO2 on 400 ppm ja anna komento: FF 01 87 00 00 00 00 00 78 nollapisteen kalibrointiin

- 0x88 = kalibroi span-piste
  - 0 = 0xFF, 1 = 0x01 varattu, 2 = komento 0x88, 3 = HIGH-arvo, 4 = LOW-arvo, 5-7 = 0x00, 8 = crc
  Nollapisteen kalibrointi tulee olla ensin valmis!
  Aseta sensori 2000 ppm CO2 kaasuun vähintään 20 minuutiksi.
  Mikäli span-arvo on 2000 ppm, HIGH-arvo on 2000/256, LOW-arvo on 2000 % 256
  Lähetä komento FF 01 88 07 D0 00 00 00 A0 span-pisteen kalbroimiseksi.

- 0x79 = on/off itsekalibrointi nollapisteelle (ABC-logiikka)
  - 0 = 0xFF, 1 = 0x01 varattu, 2 = komento 0x79, 3 = 0xA0/0x00, 4-7 = 0x00. 8 = crc
    - ON komento: FF 01 79 A0 00 00 00 00 E6
    - OFF komento: FF 01 79 00 00 00 00 00 86
    - Oletus on ON ja oletus CO2 ppm on 400. Kalibrointi tehdään 24 tunnin välein, mutta se ei sovellu esimerkiksi
      maatiloille, jääkaappiin tai muihin poikkeaviin tiloihin, jolloin automaattinen asetus tulee kytkeä pois ja
      kalibrointi tulee tehdä manuaalisesti.

- 0x99 = mittausvälin asetus
  - 0 = 0xFF, 1 = 0x01 varattu, 2 = komento 0x99, 3 = 0x00 varattu, 4 = mittausalue 24 ~ 32 bit, 5 = 16 ~ 23 bit,
    6 = 8 ~15 bit, 7 = 0~7 bit, 8 = crc
    Mittausalueen tulee olla 0~2000, 0~5000, tai 0~10000ppm
    0~2000ppm alue komennolla: FF 01 99 00 00 00 07 D0 8F
    0~10000ppm alue komennolla: FF 01 99 00 00 00 27 10 2F


Kytkentä:
    - ESP32 UART0 on varattu USB serialille, eli käytä UART1 tai 2, esim. pinnit 16(rx) ja 17(tx).
    - sensorin tx (transmit) menee ESP:n rx (receive)

Lainattu peruslukua https://github.com/dr-mod/co2-monitoring-station/blob/master/mhz19b.py

3.12.2020 Jari Hiltunen
4.12.2020 UART:ssa read ja write metodit pysäyttävät toiminnan luvun tai kirjoituksen ajaksi. Muutettu
   käyttämään stremia 6.3 mukaisesti:
   https://github.com/peterhinch/micropython-async/blob/master/v3/docs/TUTORIAL.md#63-using-the-stream-mechanism
   Luokassa MHZ19bCO2 on mm. muutettu self.sensori.write(self.LUKU_KOMENTO) -> await self.kirjoittaja(self.LUKU_KOMENTO)

"""


import machine
import utime
import uasyncio as asyncio


class MHZ19bCO2:

    def __init__(self, rxpin=16, txpin=17):
        self.sensori = machine.UART(1)
        self.sensori.init(baudrate=9600, bits=8, parity=None, stop=1, rx=rxpin, tx=txpin)
        self.nollapiste_kalibroitu = False
        self.co2_arvo = 0
        self.co2_keskiarvot = []
        self.co2_keskiarvoja = 20
        self.co2_keskiarvo = 0
        self.sensori_aktivoitu_klo = utime.time()
        self.arvo_luettu_klo = utime.time()
        self.mittausvali = '0_5000'
        self.esilammitysaika = 10   # tulee olla 180
        self.lukuvali = 10  # tulee olla 120
        self.LUKU_KOMENTO = bytearray(b'\xFF\x01\x86\x00\x00\x00\x00\x00\x79')
        self.KALIBROI_NOLLAPISTE = bytearray(b'\xFF\x01\x87\x00\x00\x00\x00\x00\x78')
        self.KALIBROI_SPAN = bytearray(b'\xFF\x01\x88\x07\xD0\x00\x00\x00\xA0')
        self.ITSEKALIBROINTI_ON = bytearray(b'\xFF\x01\x79\xA0\x00\x00\x00\x00\xE6')
        self.ITSEKALIBTOINTI_OFF = bytearray(b'\xFF\x01\x79\x00\x00\x00\x00\x00\x86')
        self.MITTAUSVALI_0_2000PPM = bytearray(b'\xFF\x01\x99\x00\x00\x00\x07\xD0\x8F')
        self.MITTAUSVALI_0_5000PPM = bytearray(b'\xFF\x01\x99\x00\x00\x00\x13\x88\xCB')
        self.MITTAUSVALI_0_10000PPM = bytearray(b'\xFF\x01\x99\x00\x00\x00\x27\x10\x2F')

    async def kirjoittaja(self, data):
        portti = asyncio.StreamWriter(self.sensori, {})
        portti.write(data)
        await portti.drain()    # Lähetys alkaa
        await asyncio.sleep(2)

    async def lukija(self, merkkia):
        portti = asyncio.StreamReader(self.sensori)
        data = await portti.readexactly(merkkia)
        return data

    async def lue_co2_looppi(self):
        while True:
            if (utime.time() - self.sensori_aktivoitu_klo) < self.esilammitysaika:
                #  Esilämmitysaika on 3 minuuttia
                print("Esilämmitysajalla ... odottele")
                await asyncio.sleep(1)
            elif (utime.time() - self.arvo_luettu_klo) > self.lukuvali:
                #  Luetaan arvoja korkeintaan 2 min välein
                print("Luetaan arvo, hetki...")
                try:
                    # self.sensori.write(self.LUKU_KOMENTO)
                    await self.kirjoittaja(self.LUKU_KOMENTO)
                    lukukehys = bytearray(await self.lukija(9))
                    if lukukehys[0] == 0xff and self._laske_crc(lukukehys) == lukukehys[8]:
                        self.co2_arvo = self._data_to_co2_level(lukukehys)
                        # print(self.co2_arvo)
                        self.laske_keskiarvo(self.co2_arvo)
                        self.arvo_luettu_klo = utime.time()
                except TypeError as e:
                    print("Virhe %s", e)
                    pass
            await asyncio.sleep(self.lukuvali)

    def laske_keskiarvo(self, co2):
        self.co2_keskiarvot.append(co2)
        self.co2_keskiarvo = (sum(self.co2_keskiarvot) / len(self.co2_keskiarvot))
        #  20 arvoa ja poistetaan vanhin
        if len(self.co2_keskiarvot) == self.co2_keskiarvoja:
            self.co2_keskiarvot.pop(0)

    def kalibroi_nollapiste(self):
        if utime.time() - self.sensori_aktivoitu_klo > (20 * 60):
            self.kirjoittaja(self.KALIBROI_NOLLAPISTE)
            self.nollapiste_kalibroitu = True
        else:
            print("Ennen kalibrointia sensorin tulee olla lämmennyt 20 minuuttia!")

    def kalibroi_span(self):
        if self.nollapiste_kalibroitu is True:
            self.kirjoittaja(self.KALIBROI_SPAN)
        else:
            print("Nollapistee tulee olla ensin kablinroituna!")

    def itsekalibrointi_on(self):
        self.kirjoittaja(self.ITSEKALIBROINTI_ON)

    def itsekalibrointi_off(self):
        self.kirjoittaja(self.ITSEKALIBTOINTI_OFF)

    def mittausvali_0_2000_ppm(self):
        self.kirjoittaja(self.MITTAUSVALI_0_2000PPM)
        self.mittausvali = '0_2000'

    def mittausvali_0_5000_ppm(self):
        self.kirjoittaja(self.MITTAUSVALI_0_5000PPM)
        self.mittausvali = '0_5000'

    def mittausvali_0_10000_ppm(self):
        self.kirjoittaja(self.MITTAUSVALI_0_10000PPM)
        self.mittausvali = '0_10000'

    @staticmethod
    def _laske_crc(lukukehys):
        if len(lukukehys) != 9:
            return None
        crc = sum(lukukehys[1:8])
        return (~(crc & 0xff) & 0xff) + 1

    @staticmethod
    def _data_to_co2_level(data):
        return data[2] << 8 | data[3]
