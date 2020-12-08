"""
For ESP32-Wrover or ESP32-Wroom. Controls solar panel towards the sun peak position.

Battery voltage measurement: voltage splitter 2 x 100 kOhm resistors so that another end is at + , another -
 and from the middle to the IO-port (BATTERY_ADC_PIN).

 ESP32 ADC in 12 bit 4096 steps, when 3.3 volts / 4096 = 0,0008056V per step, but
 because we use voltage splitter, value needs to be multiplied with 2, when each change in reading means
 0,0016113 volts per step. Checking with multimeter: measure volts from voltage splitter, shall be always below 3.3V,
 which is port maximum. As an example, 3,28 volts at the battery shows 1,65V at the voltage splitter. However, this
 is not enough, because ESP32 reads ADC values between 0 - 1 volts. That is why we need 11DB attennuation in the
 port initialization. Checking values read:

    voltagelist = []
    while len(voltagelist) < 5000:
    lista.append(batteryvoltage.read())

    --> 5000 value list brings min = 1657 and max(voltagelist) = 1958. Average is 1796.592.

 We know from multimeter reading that battery real voltage is 3.28V. Devide voltage / 1796.592, when we end up to
 multiplier 0.00182567 volts per ADC bit. But is ADC with attennuation linear? No, it is not!

 Linearity we can check with other voltage, say 4.66 volts, which brings 2.3 volts to the voltage splitter, and from
 ADC read minimum we see value 2500, maximum 2735, average 2614.584, so 4.66 volts / 2614.584 = 0.0017823 V/b

 Best educated guess for the proper multiplies is 0.0018V per bit with 11DB attennuation.

Stepper motor control: stepper motor is rotated back and fort x steps and during each step voltage from the
 solar panel is measured. A list of steps and voltages is created and maximum is selected. If maximum resides
 in clockwise steps, within 1 - x steps, we select highest voltage step, otherwise step must be in counterclockwise
 steps, steps + step. Once this phase is complete, we know how much we need to turn solar panel to get
 always highest input. Last we check time, calculate how much we must turn stepper motor each minute to keep on
 track with the sun. Rough estimate is to use localtime 12:00 for south position. Calibration is completed once a day.


7.12.2020 Jari Hiltunen
8.12.2020 Initial version ready before class splitting. Stepper shall follow the sun.

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
        self.steps_to_rotate = 10  # Default for testing
        self.max_voltage = None
        self.step_max_index = None
        self.panel_time = None
        self.uptime = 0
        self.direction = None
        self.degrees_minute = 360 / (24 * 60)
        self.full_rotation = int(4075.7728395061727 / 8)  # http://www.jangeox.be/2013/10/stepper-motor-28byj-48_25.html
        self.steps_for_minute = int((24 * 60) / self.full_rotation)  # 0.17 steps rounded

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
        """ Limiter switches not yet supported. Stepstorotate to both directions from startup! """
        print("Finding highest voltage direction for the solar panel. Wait.")
        self.steps_to_rotate = stepstorotate
        await self.zero_to_potision()    # typo is in the class
        #  Look steps clockwise
        print("Turning panel clockwise %s steps" % self.steps_to_rotate)
        for i in range(0, self.steps_to_rotate):
            await self.turn_x_steps_right(1)
            await asyncio.sleep(1)
            self.battery_voltage = batteryreader.read()
            if self.battery_voltage is not None:
                self.steps_voltages.append(self.battery_voltage)
        await self.turn_x_steps_left(self.steps_to_rotate)
        await asyncio.sleep(1)
        #  Look steps counterclockwise
        print("Turning panel counterclockwise %s steps" % self.steps_to_rotate)
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
        #  Now we have voltages to both directions, check which one has highest voltage. First occurence.
        self.max_voltage = max(self.steps_voltages)
        self.step_max_index = self.steps_voltages.index(max(self.steps_voltages))
        #  Panel at highest solar power direction, if time is correct, calculate direction
        self.panel_time = utime.localtime()
        #  The sun shall be about south at LOCAL 12:00 winter time (summer +1h)
        self.direction = (int(self.panel_time[3] * 60) + int(self.panel_time[4])) * self.degrees_minute
        if self.step_max_index <= self.steps_to_rotate:
            """ Maximum voltage value found from first right turn, maximum counterwise """
            await self.turn_x_steps_right(self.step_max_index)
        elif self.step_max_index > self.steps_to_rotate:
            """ Maximum voltage value found from second turn, maximum counterclocwise """
            await self.turn_x_steps_left(self.step_max_index - self.steps_to_rotate)

    async def follow_the_sun_loop(self):
        #  Execute once a minute. Drift 0.17 steps / minute, add step each 6 minutes !
        c = 0
        while True:
            if self.panel_time is not None:
                self.uptime = utime.mktime(utime.localtime()) - \
                              utime.mktime(self.panel_time)
            #  If second is 00, do turn
            if int(utime.localtime()[5]) == 0:
                await self.turn_x_steps_right(self.steps_for_minute)
                self.direction = self.direction + self.degrees_minute
                await asyncio.sleep(1)
                c += 1
                if c == 6:
                    await self.turn_x_steps_right(1)
                    c = 0
            await asyncio.sleep_ms(500)


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
        print("Best position: %s/%s degrees, voltage %s, step %s.  "
              % (panel_motor.panel_time, panel_motor.direction, panel_motor.max_voltage, panel_motor.step_max_index))
    elif (utime.mktime(utime.localtime()) - panel_motor.uptime) > 1440:
        await panel_motor.search_best_voltage_position()
        print("Best position: %s/%s degrees, voltage %s, step %s.  "
              % (panel_motor.panel_time, panel_motor.direction, panel_motor.max_voltage, panel_motor.step_max_index))
    asyncio.create_task(panel_motor.follow_the_sun_loop())

    while True:
        print("Panel direction: %s, uptime %s" % (panel_motor.direction, panel_motor.uptime))
        await asyncio.sleep(5)

asyncio.run(main())
