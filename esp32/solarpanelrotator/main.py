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
17.2.2021 Added limiter switch operation. Limiter switch is installed so that turning counterclockwise switch
          puller pushes the switch down. Counterwise turn must be limited to maximum steps (about 340 degrees rotation).
          Added solarpanel voltage reading.

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
        STEPPER1_DELAY, MICROSWITCH_PIN, SOLARPANEL_ADC_PIN
except OSError:  # open failed
    print("parameter.py-file missing! Can not continue!")
    raise


""" Global objects """
batteryreader = ADC(Pin(BATTERY_ADC_PIN))
# Attennuation below 1 volts 11 db
batteryreader.atten(ADC.ATTN_11DB)
solarpanelreader = ADC(Pin(SOLARPANEL_ADC_PIN))
solarpanelreader.atten(ADC.ATTN_11DB)

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


class StepperMotor(object):
    """ ULN2003-based control, half steps. Asynchronous setup. """

    def __init__(self, in1, in2, in3, in4, indelay):
        self.motor = Steppermotor.create(Pin(in1, Pin.OUT), Pin(in2, Pin.OUT), Pin(in3, Pin.OUT),
                                         Pin(in4, Pin.OUT), delay=indelay)
        self.stepdelay = indelay
        self.solar_voltage = None
        self.steps_voltages = []
        self.max_steps_to_rotate = 900  # almost full round
        self.max_voltage = None
        self.step_max_index = None
        self.panel_time = None
        self.uptime = 0
        self.direction = None
        self.degrees_minute = 360 / (24 * 60)
        self.full_rotation = int(4075.7728395061727 / 8)  # http://www.jangeox.be/2013/10/stepper-motor-28byj-48_25.html
        self.steps_for_minute = int((24 * 60) / self.full_rotation)  # 0.17 steps rounded
        self.table_turning = False
        self.steps_taken = 0

    async def zero_to_position(self):
        self.motor.reset()

    async def step(self, direction, overrideswitch=False):
        if direction == "cw":
            turn = -1
        elif direction == "ccw":
            turn = 1
        else:
            return False

        if overrideswitch is False:
            # switch = 1 means switch is open
            if limiter_switch.value() == 1:
                try:
                    self.motor.step(1, turn)
                    self.table_turning = True
                    await asyncio.sleep_ms(self.stepdelay)
                except OSError as ex:
                    print('ERROR %s stepping %s:' % (ex, direction))
                    await error_reporting('ERROR %s stepping %s' % (ex, direction))
                    self.table_turning = False

        if overrideswitch is True:
            try:
                self.motor.step(1, turn)
                self.table_turning = True
            except OSError as ex:
                print('ERROR %s stepping %s:' % (ex, direction))
                await error_reporting('ERROR %s stepping %s' % (ex, direction))
                self.table_turning = False
            await asyncio.sleep_ms(self.stepdelay)

    async def turn_to_limiter(self):
        print("Starting rotation counterclockwise until limiter switch turns off...")
        starttime = utime.ticks_ms()
        while limiter_switch.value() == 1 and ((utime.ticks_ms() - starttime) < 90000):
            await self.step("ccw")
            self.steps_taken = +1
        print("Switch on, taking a few steps back to open the switch...")
        self.steps_taken = 0
        # Take a few steps back to open the switch
        while limiter_switch.value() == 0:
            await self.step("cw", overrideswitch=True)
            self.steps_taken = +1
        self.table_turning = False

    async def search_best_voltage_position(self):
        print("Finding highest voltage direction for the solar panel. Wait.")
        await self.turn_to_limiter()
        #  Look steps clockwise
        print("Turning panel clockwise %s steps" % self.max_steps_to_rotate)
        for i in range(0, self.max_steps_to_rotate):
            await self.step("cw")
            await asyncio.sleep_ms(10)
            self.solar_voltage = solarpanelreader.read()
            if self.solar_voltage is not None:
                print("Voltage %s" % self.solar_voltage)
                self.steps_voltages.append(self.solar_voltage)
        if len(self.steps_voltages) < self.max_steps_to_rotate:
            print("Some values missing! Should be %s, is %s" % (self.max_steps_to_rotate, len(self.steps_voltages)))
            return False
        #  Now we have voltages for each step, check which one has highest voltage. First occurence.
        self.max_voltage = max(self.steps_voltages)
        self.step_max_index = self.steps_voltages.index(max(self.steps_voltages))
        #  Panel at highest solar power direction, if time is correct, calculate direction
        self.panel_time = utime.localtime()
        #  The sun shall be about south at LOCAL 12:00 winter time (summer +1h)
        self.direction = (int(self.panel_time[3] * 60) + int(self.panel_time[4])) * self.degrees_minute
        """ Maximum voltage value found. Turn to maximum"""
        print("Rotating back to maximum %s steps" % (self.max_steps_to_rotate - self.step_max_index))
        for i in range(0, (self.max_steps_to_rotate - self.step_max_index)):
            await self.step("ccw")
        self.table_turning = False

    async def follow_the_sun_loop(self):
        #  Execute once a minute. Drift 0.17 steps / minute, add step each 6 minutes !
        c = 0
        while True:
            if self.panel_time is not None:
                self.uptime = utime.mktime(utime.localtime()) - \
                              utime.mktime(self.panel_time)
            #  If second is 00, do turn
            if int(utime.localtime()[5]) == 0:
                print("Rotate %s steps counterwise." % self.steps_for_minute)
                self.table_turning = True
                for i in range(0, self.steps_for_minute):
                    await self.step("cw")
                self.direction = self.direction + self.degrees_minute
                await asyncio.sleep(1)
                c += 1
                if c == 6:
                    print("Rotate 1 step right for correction.")
                    await self.step("cw")
                    c = 0
            else:
                self.table_turning = False
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


#  First initialize limiter_switch object, then panel motor
limiter_switch = Pin(MICROSWITCH_PIN, Pin.IN, Pin.PULL_UP)
panel_motor = StepperMotor(STEPPER1_PIN1, STEPPER1_PIN2, STEPPER1_PIN3, STEPPER1_PIN4, STEPPER1_DELAY)


async def read_battery_level():
    while True:
        pass
        # print("Battery level: %s" % batteryreader.read())


async def report_what_i_do():
    while True:
        print("Limiter switch is %s" % limiter_switch.value())
        print("Turntable turning %s" % panel_motor.table_turning)
        print("Panel direction: %s, uptime %s" % (panel_motor.direction, panel_motor.uptime))
        await asyncio.sleep(2)


async def main():
    MQTTClient.DEBUG = False
    # await client.connect()
    loop = asyncio.get_event_loop()
    loop.create_task(read_battery_level())
    loop.create_task(report_what_i_do())

    #  Find best step and direction for the solar panel. Do once when boot, then once a day
    if panel_motor.panel_time is None:
        await panel_motor.search_best_voltage_position()
        print("Best position: %s/%s degrees, voltage %s, step %s.  "
              % (panel_motor.panel_time, panel_motor.direction, panel_motor.max_voltage, panel_motor.step_max_index))
    elif (utime.mktime(utime.localtime()) - panel_motor.uptime) > 86400:
        await panel_motor.search_best_voltage_position()
        print("Best position: %s/%s degrees, voltage %s, step %s.  "
              % (panel_motor.panel_time, panel_motor.direction, panel_motor.max_voltage, panel_motor.step_max_index))

    loop.create_task(panel_motor.follow_the_sun_loop())

    loop.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except MemoryError:
        reset()
