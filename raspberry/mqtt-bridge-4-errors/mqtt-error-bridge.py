'''

24.9.2020: MQTT-2-ErrorFile-loggeri

Tämä versio on tarkoitettu mqtt-virhesanomien siirtämiseen virhetiedostoon.
MQTT-sanoma voi olla esimerkiksi muotoa virheet/sijainti/laite (määritä parametrit.py-tiedostossa)
 --> virheviestin rakenne: pvm + aika;uptime;laitenimi;ip;virhe;vapaa muisti

Kaikki datatyypit ovat str.

Lainattu koodia mqtt-influxdb-bridge-koodista https://diyi0t.com/visualize-mqtt-data-with-influxdb-and-grafana/.

'''

import re
from typing import NamedTuple
import paho.mqtt.client as mqtt
import logging.handlers
from parametrit import MQTTSERVERI, MQTTSALARI, MQTTKAYTTAJA, MQTTSERVERIPORTTI

''' Tässä kiinteänä virheet ensimmäisenä tasona. Huomaa alempana luokka SensorData '''
MQTT_TOPIC = 'virheet/+/+'
MQTT_REGEX = 'virheet/([^/]+)/([^/]+)'
MQTT_CLIENT_ID = 'MQTTErrorLoggeri'

''' Muuta logitiedoston polkua ja nimeä tarpeen mukaan. Tuotetaan megan kokoisia logitiedostoja max 5 kpl. '''
LOG_FILENAME = 'mqtt-silta-virheille.out'
loggeri = logging.getLogger('MQTT-VirheLoggeri')
loggeri.setLevel(logging.DEBUG)
handleri = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=1000000, backupCount=5)
loggeri.addHandler(handleri)


class SensorData(NamedTuple):
    """ Käsiteltävät tasot ja varsinainen virhe """
    sijainti: str
    laite: str
    virhe: str


def on_connect(client, userdata, flags, rc):
    """ Yhdistys MQTT-topicciin """
    print('Yhdistetty tilakodilla: ' + str(rc))
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    """ Suoritetaan kun viesti saapuu brokerilta """
    print(msg.topic + ' ' + str(msg.payload))
    sensor_data = _parse_mqtt_message(msg.topic, msg.payload.decode('utf-8'))
    if sensor_data is not None:
        _send_sensor_data_to_errorfile(sensor_data)


def _parse_mqtt_message(topic, payload):
    """ Parsitaan viestistä virheilmoitus """
    match = re.match(MQTT_REGEX, topic)
    if match:
        sijainti = match.group(1)
        laite = match.group(2)
        return SensorData(sijainti, laite, payload)
    else:
        return None


def _send_sensor_data_to_errorfile(sensor_data):
    """ Tuotetaan json-rakenne ja tallennetaan logitiedostoon"""
    json_body = [
        {
            'laite': sensor_data.laite,
            'sijainti': sensor_data.sijainti,
            'virhe':  sensor_data.virhe
        }
    ]
    loggeri.debug(json_body)


def main():
    mqtt_client = mqtt.Client(MQTT_CLIENT_ID)
    mqtt_client.username_pw_set(MQTTKAYTTAJA, MQTTSALARI)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTTSERVERI, MQTTSERVERIPORTTI)
    mqtt_client.loop_forever()

if __name__ == '__main__':
    print('MQTT to Error Log bridge')
    main()
