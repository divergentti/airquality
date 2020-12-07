"""
Tämä suurimmaksi osaksi deep sleepissä aikaa viettävä scripti on tarkoitettu ESP32-Wroom-NodeMCU:lle.

Tarkoituksena on käyttää pelkkää piiriä, eli kytkentään esimerkiksi träppilanka juottamalla piiriin
ja otetaan siitä suoraan lähtö AM2302 (DHT22)-sensorille. Minimoimalla virrankulutuksen voidaan piiri ja anturi
sijoittaa esimerkiksi ullakolle ja tällöin esimerkiksi paristo tai akku kestää kuukausia.

Kevyessä unessa piiri kuluttaa 0,8mA, syväunessa jossa käytössä on RTC ajastin ja RTC muisti, jota tässä scripitssä
hyödynnetään, kulutus on 10 uA.

Sensori kuluttaa mitatessaan noin 0,5mA ja anturin minimi lukuväli on 2 sekuntia.

Piiri ohjelmoidaan erillisellä ohjelmointilaitteella, joita saa ostettua nimellä "ESP-WROOM-32
Development Board Test Burning Fixture Tool Downloader". Laitteen hinta on noin 10€ ja ESP-piirien
noin 2€ kappale. Itse suosin U-mallista piiriä, johon tarvitaan erillinen antenni, joita löytyy nimellä
2.4GHz 3dBi WiFi Antenna Aerial RP-SMA Male wireless router+ 17cm PCI U.FL IPX to RP SMA Male Pigtail Cable.

Kytkennässä tulee muistaa kytkeä EN-nasta 3,3 voltin jännitteeseen! Viemällä nasta EN tilaan HIGH
piiri kytketään käyttöön. Tarvitaan siis VCC, GND ja AM2302 sensorilta data sopivaan nastaan, esim. IO4.

Testien perusteella WiFi-yhteyden palauttaminen ja kolmen mittauksen luenta ja niiden keskiarvojen lähtys
mqtt brokerille näkyy noin 10 pingin verran, eli aikaa kuluu noin 10 sekuntia päällä. Yleismittarilla mitattuna
maksimikulutus on tuona aikana noin 27mA ja tippuu sen jälkeen alle 1mA arvoon, eli arvoa ei voi lukea.

Tekniset tiedot ESP32-piiristä https://www.espressif.com/en/support/documents/technical-documents
Tekniset tiedot AM2303-sensorista https://datasheetspdf.com/pdf-file/845488/Aosong/AM2303/1


15.10.2020 Jari Hiltunen

Muutokset: 20.10.2020: Listätty client.disconnect, sillä yhteys voi olla päällä edellisestä kerrasta ja lisätty
akkujännitteen mittaus.

Akkujännite viedään kahden samanarvoisen vastuksen, esimerkiksi 100kOhm (jännitteen jakaja)
avulla GPIO:n. Vastukset kytketään akun + ja - napoihin ja keskeltä GPIO-porttiin. ESP32:n ADC:ssa voidaan
GPIO-pinnissä erottaa 12 bitin tilassa 4096 tilaa, eli 3,3 volttia / 4096 -> 0,8056 per tila, mutta koska käytämme
jännitteen jakajaa, tulee tämä kertoa kahdella, eli vakioksi muodostuu laskennallisesti 1,6113. Vakion tarkistaminen
yleismittarilla: esimerkiksi jännite 3,28 voltista 2 x 100 kOhm splitterillä tuottaa GPIO-pínniin 1,65V,
joka näkyy 11DB vaimennuksella seuraavasti:

lista = []
while len(lista) < 5000:
    lista.append(akkujannite.read())

--> 5000 arvon listassa min(lista) = 1657 ja max(lista) = 1958. Keskiarvo sum(lista)/len(lista) 1796,592.

Tästä saamme laskettua 3,28V / 1796,592 = 0,00182567V per ADC bitti, mutta koska mittaus ei ole kovin lineaarinen
ja sisältää häiriöitä, ei kerroin ole kovin tarkka. Esimerkiksi tuomalla jännitteen 4,66V splitteriin saamme GPIO:n
jännitteeksi 2,3V ja arvoiksi: minimi = 2500, maksimi 2735, keskiarvo 2614,584 -> 4,66V / 2614,584 = 0,0017823V/b

Sopiva kerroin on tällöin aika liki 0,0018V per bitti, jolloin esimerkiksi mitattu arvo 1796 * 0,0018 = 3,23V.

Kerroin tuodaan parametrit.py-tiedostosta AKKU_VAKIO:na.

Huom! Vastus voi minimissään olla 47 kOhm, jolloin kulutus on luokkaa 50 uA ja mitä suuremmat vastukset,
sitä pienempi virrankulutus, mutta toisaalta lisää mahdollisuutta häiriöille.Käytä pinnejä 34 - 39 inputteihin,
sillä niissä ei ole pull-up vastuksia ja ovat ADC1:ssä, joka toimii WiFin kanssa.

Maksimiarvo 4095 saadaan jännitteellä 1v ja tästä syystä ADC lukua vaimennetaan 11 db, jolloin 0 - 4095
vastaa jännitealuetta 0,0v - 3,6v. Jännite GPIO-portissa ei saa koskaan nousta yli 3,6 voltin!

Jännitetieto lähetetään AIHE_JANNITE mukaisella mqtt-viestillä.

22.10.2020: Koska tarkoitus on kuluttaa mahdollisimman vähän virtaa, akkutoteutus ei ole järkevä. Näin ollen
tarvitaan kaksi erillistä piiriä, CR123a litiumparistolta ESP:lle ja ESP:n käynnistämä toisiopiiri DC-pumpulle,
joka nostaa CR123a jännitteen (1,8 - 5V) AM2302 tarvitsemaan 3,3 volttiin. Tällöin ESP:n nukkuessa AM2302 sensori
tai mikään toisiopiirissä oleva ei kuluta virtaa, vaan kulutus on ainostaan ESP:n syväyni noin 7 uA.
Huomaa, että 36 -> ovat vain inputteja, eli käytä jotain alempaa IO:ta, kuten IO13 ja tilassa Open Drain. Pinni
laitetaan maihin, jolloin piiri aktivoituu. ESP32 toimii 2.3 volttiin saakka luotettavasti. Mikäli jännite on 2.3V
tulisi EN-pinni laittaa maihin, eli toiminta sulkea.

Sekä AM2302 että akkujännitteen mittaukseen tarkoitettu maa (GND) kytketään TOISIOPIIRI_AKTIVAATIO_PINNI kautta.

"""
import time
import machine
import dht
from machine import Pin
from machine import ADC
from umqttsimple import MQTTClient

# tuodaan parametrit tiedostosta parametrit.py
try:
    from parametrit import CLIENT_ID, MQTT_SERVERI, MQTT_PORTTI, MQTT_KAYTTAJA, MQTT_SALASANA, DHT22_LAMPO, \
        DHT22_KOSTEUS, DHT_PINNI_NUMERO, DHT22_LAMPO_KORJAUSKERROIN, DHT22_KOSTEUS_KORJAUSKERROIN, NUKKUMIS_AIKA, \
        AIHE_JANNITE, AKKU_ADC_PINNI, AKKU_VAKIO, TOISIOPIIRI_AKTIVOINTI_PINNI, AIHE_VIRHEET
except ImportError:
    print("Jokin asetus puuttuu parametrit.py-tiedostosta!")
    raise

#  dht-kirjasto tukee muitakin antureita kuin dht22
anturi = dht.DHT22(Pin(DHT_PINNI_NUMERO))
client = MQTTClient(CLIENT_ID, MQTT_SERVERI, MQTT_PORTTI, MQTT_KAYTTAJA, MQTT_SALASANA)
#  jännitteen mittaus
akkujannite = ADC(Pin(AKKU_ADC_PINNI))
# vaimennus 11 db
akkujannite.atten(ADC.ATTN_11DB)
#  Toisiopiirin aktivaatio. Tila 0 = GND.
toisiopiiri = Pin(TOISIOPIIRI_AKTIVOINTI_PINNI, mode=Pin.OPEN_DRAIN, pull=-1)


def lue_akkujannite():
    arvolista = []
    #  Luetaan 3 arvoa
    while len(arvolista) < 3:
        try:
            arvolista.append(akkujannite.read())
        except OSError:
            arvolista.append(0)
    #  Lasketaan keskiarvo ja kerrotaan AKKU_VAKIOLLA
    if (sum(arvolista) > 0) and len(arvolista) > 0:
        jannite = (sum(arvolista) / len(arvolista)) * AKKU_VAKIO
    else:
        jannite = 0
    return jannite

def lue_lampo_kosteus():
    """ Luetaan 2 arvoa 2s välein ja lasketaan keskiarvo, joka lähtetään mqtt:llä """
    lampo_lista = []  # keskiarvon laskentaa varten
    rh_lista = []  # keskiarvon laskentaa varten
    lukukertoja = 0
    lampo_keskiarvo = 0
    rh_keskiarvo = 0

    while lukukertoja < 2:
        try:
            anturi.measure()
        except OSError:
            print("Sensoria ei voida lukea!")
            return False
        lampo = anturi.temperature() * DHT22_LAMPO_KORJAUSKERROIN
        # print('Lampo: %3.1f C' % lampo)
        if (lampo > -40) and (lampo < 100):
            lampo_lista.append(lampo)
        kosteus = anturi.humidity() * DHT22_KOSTEUS_KORJAUSKERROIN
        # print('Kosteus: %3.1f %%' % kosteus)
        if (kosteus > 0) and (kosteus <= 100):
            rh_lista.append(kosteus)
        if len(lampo_lista) == 2:
            lampo_keskiarvo = sum(lampo_lista) / len(lampo_lista)
            rh_keskiarvo = sum(rh_lista) / len(rh_lista)
        time.sleep(2)
        lukukertoja = lukukertoja+1
    return [lampo_keskiarvo, rh_keskiarvo]


def laheta_arvot_mqtt(lampo_in, kosteus_in, akku_in):
    lampof = '{:.1f}'.format(lampo_in)
    kosteusf = '{:.1f}'.format(kosteus_in)
    #  Muodostetaan hälytys jos jännite on 2.5 tai alle.
    if akku_in <= 2.5:
        try:
            client.publish(AIHE_VIRHEET, "Aika vaihtaa %s paristo! Jännite %sV" % (CLIENT_ID, str(akku_in)))
            # print("Aika vaihtaa %s paristo! Jännite %sV" % (CLIENT_ID, str(akku_in)))
        except OSError:
            return False
    try:
        client.publish(DHT22_LAMPO, str(lampof))
    except OSError:
        return False
    try:
        client.publish(DHT22_KOSTEUS, str(kosteusf))
    except OSError:
        return False
    try:
        client.publish(AIHE_JANNITE, str(akku_in))
    except OSError:
        return False
    # print("MQTT:lle %sC, %s, %sV" % (lampof, kosteusf, akku_in))
    return True


def restart_and_reconnect():
    # print('Ongelmia. Boottaillaan.')
    machine.reset()
    # resetoidaan


try:
    client.connect()
except OSError:
    # print("Ei voida yhdistaa mqtt! ")
    restart_and_reconnect()

while True:
    lampo = None
    kosteus = None
    #  Aktivoidaan toisiopiiri liittämällä maa piiriin
    toisiopiiri(0)
    #  DHT aktivaatiolle hieman aikaa
    time.sleep(1)
    akkutila = lue_akkujannite()
    try:
        lampo, kosteus = lue_lampo_kosteus()
    except TypeError:
        pass
    #  Inaktivoidaan toisiopiiri
    toisiopiiri(1)
    if (lampo is not None) and (kosteus is not None):
        laheta_arvot_mqtt(lampo, kosteus, akkutila)
    try:
        client.disconnect()
    except OSError:
        pass
    except KeyboardInterrupt:
        raise
    # print("Nukkumaan %s millisekunniksi!" % NUKKUMIS_AIKA)
    machine.deepsleep(NUKKUMIS_AIKA)
