''' Alkuperäinen https://gist.github.com/zufardhiyaulhaq/fe322f61b3012114379235341b935539

Tässä versiossa olen lisännyt neljännen tason mqtt-sanomaan, joka välitetään InfluxDB-tietokantaan ja sitä kautta
esimerkiksi Grafanaan, jolla tietoa voidaan helposti visualisisoida.

MQTT-sanoma voi olla esimerkiksi muotoa koti/etela/varasto/kosteus tällä versiolla.

3.9.2020 Jari Hiltunen
'''

import re
from typing import NamedTuple

import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient

INFLUXDB_ADDRESS = 'ip address'
INFLUXDB_USER = 'username'
INFLUXDB_PASSWORD = 'password'
INFLUXDB_DATABASE = 'dbname'

MQTT_ADDRESS = 'ip'
MQTT_USER = 'user'
MQTT_PASSWORD = 'password'

''' Tässä kiinteänä koti ensimmäisenä tasona. Huomaa alempana luokka SensorData '''
MQTT_TOPIC = 'koti/+/+/+'
MQTT_REGEX = 'koti/([^/]+)/([^/]+)/([^/]+)'
MQTT_CLIENT_ID = 'MQTTInfluxDBSilta'

influxdb_client = InfluxDBClient(INFLUXDB_ADDRESS, 8086, INFLUXDB_USER, INFLUXDB_PASSWORD, None)

''' Tämä hierarkkia tulee mätsätä yllä olevaan TOPIC ja REGEX-asetukseen '''
class SensorData(NamedTuple):
    location: str
    direction: str
    measurement: str
    value: float


def on_connect(client, userdata, flags, rc):
    """ The callback for when the client receives a CONNACK response from the server."""
    print('Connected with result code ' + str(rc))
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    """The callback for when a PUBLISH message is received from the server."""
    print(msg.topic + ' ' + str(msg.payload))
    sensor_data = _parse_mqtt_message(msg.topic, msg.payload.decode('utf-8'))
    if sensor_data is not None:
        _send_sensor_data_to_influxdb(sensor_data)


def _parse_mqtt_message(topic, payload):
    match = re.match(MQTT_REGEX, topic)
    if match:
        location = match.group(1)
        ''' Tähän lisätty direction, esimerkiksi etela'''
        direction = match.group(2)
        measurement = match.group(3)
        if measurement == 'status':
            return None
        return SensorData(location, direction, measurement, float(payload))
    else:
        return None


def _send_sensor_data_to_influxdb(sensor_data):
    json_body = [
        {
            'measurement': sensor_data.measurement,
            'tags': {
                'location': sensor_data.location,
                'direction': sensor_data.direction
            },
            'fields': {
                'value': sensor_data.value
            }
        }
    ]
    influxdb_client.write_points(json_body)


def _init_influxdb_database():
    databases = influxdb_client.get_list_database()
    if len(list(filter(lambda x: x['name'] == INFLUXDB_DATABASE, databases))) == 0:
        influxdb_client.create_database(INFLUXDB_DATABASE)
    influxdb_client.switch_database(INFLUXDB_DATABASE)


def main():
    _init_influxdb_database()

    mqtt_client = mqtt.Client(MQTT_CLIENT_ID)
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    mqtt_client.connect(MQTT_ADDRESS, 1883)
    mqtt_client.loop_forever()


if __name__ == '__main__':
    print('MQTT to InfluxDB bridge')
    main()
