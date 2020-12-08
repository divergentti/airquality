"""
For ESP32-Wrover or ESP32-Wroom. Controls solar panel towards the sun

Battery voltage measurement: voltage splitter 2 x 100 kOhm resistors so that another end is at + , another -
 and from the middle to the IO-port. ESP32 ADC in 12 bit 4096 steps, when 3.3 volts / 4096 = 0,0008056V per step, but
 because we use voltage splitter, value needs to be multiplied with 2, when each change in reading means
 0,0016113 volts per step. Checking with multimeter: measure volts from voltage splitter, shall be always below 3.3V,
 which is port maximum. As an example, 3,28 volts at the battery shows 1,65V at the voltage splitter. However, this
 is not enough, because ESP32 reads ADC values between 0 - 1 volts. That is why we need 11DB attennuation in the
 port initialization. Before selecting proper multiplier, we can check what kind of values we see:

    voltagelist = []
    while len(voltagelist) < 5000:
    lista.append(batteryvoltage.read())

    --> 5000 value list brings min = 1657 and max(voltalist) = 1958. Average is 1796.592.

 We know from multimeter reading that battery voltage is 3.28V. We device voltage / 1796.592, when we end up to
 0.00182567 volts per ADC bit. But is ADC with attennuation linear? No, it is not!

 Linearity we can check with other voltage, say 4.66 volts, which brings 2.3 volts to the voltage splitter, and from
 ADC read minimum we see value 2500, maximum 2735, average 2614.584, so 4.66 volts / 2614.584 = 0.0017823 V/b

 Best educated guess for the proper multiplies is 0.0018V per bit with 11DB attennuation.

Stepper motor control: stepper motor is rotated back and fort x steps and during each step voltage from the
 solar panel is measured. Once this phase is complete, we know how much we need to turn solar panel to get
 always highest input. Time is used as reference.


7.12.2020 Jari Hiltunen

"""

import Steppermotor
from machine import Pin, ADC, reset
import uasyncio as asyncio
import utime
import gc
from MQTT_AS import MQTTClient, config
import network

try:
    f = open('parameters.py', "r")
    from parameters import SSID1, SSID2, PASSWORD1, PASSWORD2, MQTT_SERVER, MQTT_PASSWORD, MQTT_USER, MQTT_PORT, \
        CLIENT_ID, BATTERY_ADC_PIN, TOPIC_ERRORS, STEPPER1_PIN1, STEPPER1_PIN2, STEPPER1_PIN3, STEPPER1_PIN4, \
        STEPPER1_DELAY
except OSError:  # open failed
    print("parameter.py-file missing! Can not continue!")
    raise


""" Global objects """
batteryreader = ADC(Pin(BATTERY_ADC_PIN))
# Attennuation below 1 volts 11 db
batteryreader.atten(ADC.ATTN_11DB)

""" Global variables """
BATTERY_ADC_MULTIPLIER = 0.0018
previous_mqtt = utime.time()
use_wifi_password = None


""" Network setup"""
if network.WLAN(network.STA_IF).config('essid') == SSID1:
    use_wifi_password = PASSWORD1
elif network.WLAN(network.STA_IF).config('essid') == SSID2:
    use_wifi_password = PASSWORD2

config['server'] = MQTT_SERVER
config['ssid'] = network.WLAN(network.STA_IF).config('essid')
config['wifi_pw'] = use_wifi_password
config['user'] = MQTT_USER
config['password'] = MQTT_PASSWORD
config['port'] = MQTT_PORT
config['client_id'] = CLIENT_ID
client = MQTTClient(config)


def restart_and_reconnect():
    #  Last resort
    utime.sleep(5)
    reset()


class StepperMotor:
    """ ULN2003-based control, half steps. Asynchronous setup. """

    def __init__(self, in1, in2, in3, in4, indelay):
        self.motor = Steppermotor.create(Pin(in1, Pin.OUT), Pin(in2, Pin.OUT), Pin(in3, Pin.OUT),
                                         Pin(in4, Pin.OUT), delay=indelay)
        self.battery_voltage = None
        self.steps_voltages = []
        self.steps_to_rotate = 10  # Default
        self.step_max_index = None
        self.panel_time = None

    async def turn_x_degrees_right(self, degrees):
        self.motor.angle(degrees)

    async def turn_x_degrees_left(self, degrees):
        self.motor.angle(degrees, -1)

    async def turn_x_steps_right(self, steps):
        self.motor.step(steps)

    async def turn_x_steps_left(self, steps):
        self.motor.step(steps, -1)

    async def zero_to_potision(self):
        self.motor.reset()

    async def search_best_voltage_position(self, stepstorotate=10):
        """ Limiter switches not yet supported. First value is step, second voltage """
        self.steps_to_rotate = stepstorotate
        await self.zero_to_potision()    # typo is in the class
        #  Look steps clockwise
        for i in range(0, self.steps_to_rotate):
            await self.turn_x_steps_right(1)
            await asyncio.sleep(1)
            self.battery_voltage = batteryreader.read()
            if self.battery_voltage is not None:
                self.steps_voltages.append(self.battery_voltage)
        await self.turn_x_steps_left(self.steps_to_rotate)
        await asyncio.sleep(1)
        #  Look steps counterclockwise
        for i in range(0, self.steps_to_rotate):
            await self.turn_x_steps_left(1)
            await asyncio.sleep(1)
            self.battery_voltage = batteryreader.read()
            if self.battery_voltage is not None:
                self.steps_voltages.append(self.battery_voltage)
        await self.turn_x_steps_right(self.steps_to_rotate)
        if len(self.steps_voltages) < (2 * self.steps_to_rotate):
            print("Some values missing! Should be %s, is %s" % (2 * self.steps_to_rotate, len(self.steps_voltages)))
            return None
        #  Now we have voltages to both directions, check which one has highest voltage
        print(self.steps_voltages)
        self.step_max_index = self.steps_voltages.index(max(self.steps_voltages))
        if self.step_max_index <= self.steps_to_rotate:
            """ Maximum voltage value found from first right turn, maximum counterwise """
            await self.turn_x_steps_right(self.step_max_index)
        elif self.step_max_index > self.steps_to_rotate:
            """ Maximum voltage value found from second turn, maximum counterclocwise """
            await self.turn_x_steps_left(self.step_max_index - self.steps_to_rotate)
        #  Panel at highest solar power direction, if time is correct, calculate direction
        self.panel_time = utime.localtime()


async def resolve_date():
    (year, month, mdate, hour, minute, second, wday, yday) = utime.localtime()
    date = "%s.%s.%s time %s:%s:%s" % (mdate, month, year, "{:02d}".format(hour), "{:02d}".format(minute), "{:02d}".
                                       format(second))
    return date


async def error_reporting(error):
    # error message: date + time;uptime;devicename;ip;error;free mem
    errormessage = str(resolve_date()) + ";" + str(utime.ticks_ms()) + ";" \
        + str(CLIENT_ID) + ";" + str(network.WLAN(network.STA_IF).ifconfig()) + ";" + str(error) +\
        ";" + str(gc.mem_free())
    await client.publish(TOPIC_ERRORS, str(errormessage), retain=False)


async def mqtt_report():
    global previous_mqtt
    n = 0
    while True:
        await asyncio.sleep(5)
        # print('mqtt-publish', n)
        await client.publish('result', '{}'.format(n), qos=1)
        n += 1
        """ if (kaasusensori.eCO2_keskiarvo > 0) and (kaasusensori.tVOC_keskiarvo > 0) and \
                (utime.time() - previous_mqtt) > 60:
            try:
                await client.publish(AIHE_CO2, str(kaasusensori.eCO2_keskiarvo), retain=False, qos=0) """


panel_motor = StepperMotor(STEPPER1_PIN1, STEPPER1_PIN2, STEPPER1_PIN3, STEPPER1_PIN4, STEPPER1_DELAY)


async def main():
    MQTTClient.DEBUG = False
    # await client.connect()

    #  Find best step and direction for the solar panel. Do once when boot, then once a day
    if panel_motor.panel_time is None:
        await panel_motor.search_best_voltage_position()
    elif (utime.localtime() - panel_motor.panel_time) > 1440:
        await panel_motor.search_best_voltage_position()
    # asyncio.create_task(xxx)

    while True:
        print("Kukkuluuruu")

        await asyncio.sleep(5)

asyncio.run(main())
