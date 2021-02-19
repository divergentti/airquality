"""
For ESP32-Wrover or ESP32-Wroom in ULP (Ultra Low Power) mode.

Turns solar panel towards the sun and measures with BME280 temperature, humidity and pressure and sends information
to the mqtt broker and then sleeps. Calibrates once a day to the highest voltage from solarpanel.

Motor: 5V 28BYJ-48-5V and Steppermotor.py original https://github.com/IDWizard/uln2003/blob/master/uln2003.py
Solarpanel: CNC110x69-5 volts
Batteries: NCR18650B
Charger: TP4056 USB 5V 1A 18650 charger

Battery voltage and solar panel voltage measurement: voltage splitter 2 x 100 kOhm resistors so that another end
is at + , another - and from the middle to the IO-port (BATTERY_ADC_PIN and SOLARPANEL_ADC_PIN).

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

Stepper motor control: stepper motor is rotated to the limiter switch (zero position) and then almost full round.
During rotation, each step measures solarpanel voltage and best direction (first peak voltage) is chosen.
This also estimates direction of the sun, because if clock is set correctly, we can calculate in which direction
the sun is, which also means best voltage.

3D model for the case at https://gallery.autodesk.com/fusion360/users/4HPYK2VXATYM
3D printable case at https://www.thingiverse.com/thing:4758620


7.12.2020 Jari Hiltunen project start
8.12.2020 Initial version ready before class splitting. Stepper shall follow the sun.
17.2.2021 Added limiter switch operation. Limiter switch is installed so that turning counterclockwise switch
          puller pushes the switch down. Counterwise turn must be limited to maximum steps (about 340 degrees rotation).
          Added solarpanel voltage reading.
18.2.2021: Changed to non-asynchronous model, because it does not make sense to have async in ULP mode.
           Corrected voltage values to conform voltage splitter values (divide by 2).
           Ready to go with MQTT and BME280
19.2.2021: Added error handling, runtimeconfig.json handling, rotation based on time differences.
"""

import Steppermotor
from machine import I2C, Pin, ADC, reset, deepsleep
from utime import sleep, localtime, mktime, ticks_ms
import gc
from umqttsimple import MQTTClient
import network
from json import load, dump
import BME280_float as BmE

try:
    f = open('parameters.py', "r")
    from parameters import SSID1, SSID2, PASSWORD1, PASSWORD2, MQTT_SERVER, MQTT_PASSWORD, MQTT_USER, MQTT_PORT, \
        CLIENT_ID, BATTERY_ADC_PIN, TOPIC_ERRORS, STEPPER1_PIN1, STEPPER1_PIN2, STEPPER1_PIN3, STEPPER1_PIN4, \
        STEPPER1_DELAY, MICROSWITCH_PIN, SOLARPANEL_ADC_PIN, TOPIC_TEMP, TOPIC_PRESSURE, TOPIC_HUMIDITY, \
        TOPIC_BATTERY_VOLTAGE, I2C_SCL_PIN, I2C_SDA_PIN, SECONDARY_ACTIVATION_PIN
    f.close()
except OSError:  # open failed
    print("parameter.py-file missing! Can not continue!")
    raise

try:
    f2 = open('runtimeconfig.json', 'r')
    with open('runtimeconfig.json') as config_file:
        runtimedata = load(config_file)
        f2.close()
        TURNTABLE_ZEROTIME = runtimedata['TURNTABLE_ZEROTIME']
        STEPPER_LAST_STEP = runtimedata['STEPPER_LAST_STEP']
        LAST_BATTERY_VOLTAGE = runtimedata['LAST_BATTERY_VOLTAGE']
        BATTERY_LOW_VOLTAGE = runtimedata['BATTERY_LOW_VOLTAGE']
        BATTERY_LOW_VOLTAGE = BATTERY_LOW_VOLTAGE / 2  # due to voltage splitter
        BATTERY_ADC_MULTIPLIER = runtimedata['BATTERY_ADC_MULTIPLIER']
        LAST_UPTIME = runtimedata['LAST_UPTIME']
        LAST_TEMP = runtimedata['LAST_TEMP']
        LAST_HUMIDITY = runtimedata['LAST_HUMIDITY']
        LAST_PRESSURE = runtimedata['LAST_PRESSURE']
        ULP_SLEEP_TIME = runtimedata['ULP_SLEEP_TIME']
        KEEP_AWAKE_TIME = runtimedata['KEEP_AWAKE_TIME']
        DEBUG_ENABLED = runtimedata['DEBUG_ENABLED']

except OSError:
    print("Runtime parameters missing. Can not continue!")
    sleep(30)
    raise


class StepperMotor(object):

    """ ULN2003-based control, half steps. Gear ratio 0.5 : 1 """

    def __init__(self, in1, in2, in3, in4, indelay):
        self.motor = Steppermotor.create(Pin(in1, Pin.OUT), Pin(in2, Pin.OUT), Pin(in3, Pin.OUT),
                                         Pin(in4, Pin.OUT), delay=indelay)
        self.stepdelay = indelay
        self.solar_voltage = None
        self.battery_voltage = None
        self.battery_low_voltage = BATTERY_LOW_VOLTAGE
        self.steps_voltages = []
        self.max_steps_to_rotate = 900  # 1018 steps is full round, but due to microswitch reduce
        self.max_voltage = None
        self.step_max_index = None
        self.panel_time = None
        self.direction = None
        self.degrees_minute = 360 / (24 * 60)
        # Per 28BYJ motor axel, ~509 steps for full round
        self.full_rotation = int(4075.7728395061727 / 8)  # http://www.jangeox.be/2013/10/stepper-motor-28byj-48_25.html
        #  0.5 spur gear ratio (9:18 gears), half steps multiply with 2, ~ 1018 steps full round
        self.steps_for_minute = int((24 * 60) / (self.full_rotation * 2))  # 1440 / ~1018 ~ 1.4 steps per minute
        self.table_turning = False
        self.steps_taken = 0

    def zero_to_position(self):
        self.motor.reset()

    def step(self, direction, overrideswitch=False):
        self.battery_voltage = batteryreader.read() / 1000
        if self.battery_voltage < self.battery_low_voltage:
            if DEBUG_ENABLED == 1:
                print("Battery voltage %s too low!" % self.battery_voltage)
            # Report low voltage and sleep
            return
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
                except OSError as ex:
                    if DEBUG_ENABLED == 1:
                        print('ERROR %s stepping %s:' % (ex, direction))
                    error_reporting('ERROR %s stepping %s' % (ex, direction))
                    self.table_turning = False

        if overrideswitch is True:
            try:
                self.motor.step(1, turn)
                self.table_turning = True
            except OSError as ex:
                if DEBUG_ENABLED == 1:
                    print('ERROR %s stepping %s:' % (ex, direction))
                error_reporting('ERROR %s stepping %s' % (ex, direction))
                self.table_turning = False

    def turn_to_limiter(self):
        if DEBUG_ENABLED == 1:
            print("Starting rotation counterclockwise until limiter switch turns off...")
        starttime = ticks_ms()
        # Maximum time to turn full round is about 22 seconds.
        while limiter_switch.value() == 1 and ((ticks_ms() - starttime) < 22000):
            self.step("ccw")
            self.steps_taken = +1
        if DEBUG_ENABLED == 1:
            print("Switch on, taking a few steps back to open the switch...")
        self.steps_taken = 0
        # Take a few steps back to open the switch
        while limiter_switch.value() == 0:
            self.step("cw", overrideswitch=True)
            self.steps_taken = +1
        self.table_turning = False

    def search_best_voltage_position(self):
        global TURNTABLE_ZEROTIME
        self.battery_voltage = batteryreader.read() / 1000
        if self.battery_voltage < self.battery_low_voltage:
            if DEBUG_ENABLED == 1:
                print("Battery voltage %s too low!" % self.battery_voltage)
                # Report low voltage and sleep
            return
        if DEBUG_ENABLED == 1:
            print("Finding highest voltage direction for the solar panel. Wait.")
        self.turn_to_limiter()
        #  Look steps clockwise
        if DEBUG_ENABLED == 1:
            print("Turning panel clockwise %s steps" % self.max_steps_to_rotate)
        for i in range(0, self.max_steps_to_rotate):
            self.step("cw")
            self.solar_voltage = (solarpanelreader.read() / 1000) / 2  # due to voltage splitter
            if self.solar_voltage is not None:
                if DEBUG_ENABLED == 1:
                    print("Voltage %s" % self.solar_voltage)
                self.steps_voltages.append(self.solar_voltage)
        if len(self.steps_voltages) < self.max_steps_to_rotate:
            if DEBUG_ENABLED == 1:
                print("Some values missing! Should be %s, is %s" % (self.max_steps_to_rotate, len(self.steps_voltages)))
            return False
        #  Now we have voltages for each step, check which one has highest voltage. First occurence.
        self.max_voltage = max(self.steps_voltages)
        self.step_max_index = self.steps_voltages.index(max(self.steps_voltages))
        #  Panel at highest solar power direction, if time is correct, calculate direction
        self.panel_time = localtime()
        #  The sun shall be about south at LOCAL 12:00 winter time (summer +1h)
        self.direction = (int(self.panel_time[3] * 60) + int(self.panel_time[4])) * self.degrees_minute
        """ Maximum voltage value found. Turn to maximum"""
        if DEBUG_ENABLED == 1:
            print("Rotating back to maximum %s steps" % (self.max_steps_to_rotate - self.step_max_index))
        for i in range(0, (self.max_steps_to_rotate - self.step_max_index)):
            self.step("ccw")
        TURNTABLE_ZEROTIME = localtime()
        self.table_turning = False


def resolve_date():
    (year, month, mdate, hour, minute, second, wday, yday) = localtime()
    date = "%s.%s.%s time %s:%s:%s" % (mdate, month, year, "{:02d}".format(hour), "{:02d}".format(minute), "{:02d}".
                                       format(second))
    return date


def error_reporting(error):
    if network.WLAN(network.STA_IF).config('essid') != '':
        # error message: date + time;uptime;devicename;ip;error;free mem
        errormessage = str(resolve_date()) + ";" + str(ticks_ms()) + ";" \
            + str(CLIENT_ID) + ";" + str(network.WLAN(network.STA_IF).ifconfig()) + ";" + str(error) +\
            ";" + str(gc.mem_free())
        client.publish(TOPIC_ERRORS, str(errormessage), retain=False)
    else:
        if DEBUG_ENABLED == 1:
            print("Network down! Can not publish error message! Boot in 10s.")
        sleep(10)
        reset()


def mqtt_report():
    global LAST_TEMP
    global LAST_HUMIDITY
    global LAST_PRESSURE
    if network.WLAN(network.STA_IF).config('essid') != '':
        if bmes.values[0][:-1] is not None:
            client.publish(TOPIC_TEMP, bmes.values[0][:-1], retain=0, qos=0)
            LAST_TEMP = bmes.values[0][:-1]
        if bmes.values[2][:-1] is not None:
            client.publish(TOPIC_HUMIDITY, bmes.values[2][:-1], retain=0, qos=0)
            LAST_HUMIDITY = bmes.values[2][:-1]
        if bmes.values[1][:-3] is not None:
            client.publish(TOPIC_PRESSURE, bmes.values[1][:-3], retain=0, qos=0)
            LAST_PRESSURE = bmes.values[1][:-3]
    else:
        if DEBUG_ENABLED == 1:
            print("Network down! Can not publish to MQTT! Boot in 10s.")
        sleep(10)
        reset()


""" Global objects """
batteryreader = ADC(Pin(BATTERY_ADC_PIN))
# Attennuation below 1 volts 11 db
batteryreader.atten(ADC.ATTN_11DB)
solarpanelreader = ADC(Pin(SOLARPANEL_ADC_PIN))
solarpanelreader.atten(ADC.ATTN_11DB)

#  First initialize limiter_switch object, then panel motor
limiter_switch = Pin(MICROSWITCH_PIN, Pin.IN, Pin.PULL_UP)

try:
    panel_motor = StepperMotor(STEPPER1_PIN1, STEPPER1_PIN2, STEPPER1_PIN3, STEPPER1_PIN4, STEPPER1_DELAY)
except OSError as e:
    if DEBUG_ENABLED == 1:
        print("Check StepperMotor pins!!")
        raise
    else:
        raise

i2c = I2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN))

try:
    bmes = BmE.BME280(i2c=i2c)
except OSError as e:
    print("Check BME sensor I2C pins!")
    raise

# MQTT
client = MQTTClient(CLIENT_ID, MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD)

# Secondary circuit setup
secondarycircuit = Pin(SECONDARY_ACTIVATION_PIN, mode=Pin.OPEN_DRAIN, pull=-1)


def main():
    global LAST_UPTIME
    global LAST_BATTERY_VOLTAGE
    global STEPPER_LAST_STEP

    if network.WLAN(network.STA_IF).config('essid') != '':
        try:
            client.connect()
        except Exception as e:
            if type(e).__name__ == "MQTTException":
                print("** ERROR: Check MQTT server connection info, username and password! **")
                raise
            elif type(e).__name__ == "OSError":
                raise
    else:
        sleep(10)
        try:
            client.connect()
        except Exception as e:
            if type(e).__name__ == "MQTTException":
                print("** ERROR: Check MQTT server connection info, username and password! **")
                raise
            elif type(e).__name__ == "OSError":
                raise

    n = 0
    #  Activate secondary circuit. Sensors will start measuring and motor can turn.
    secondarycircuit(0)

    #  Find best step and direction for the solar panel. Do once when boot, then once a day after 7 and before 21

    if TURNTABLE_ZEROTIME is None:
        panel_motor.search_best_voltage_position()
        STEPPER_LAST_STEP = panel_motor.step_max_index
        if DEBUG_ENABLED == 1:
            print("Best position: %s/%s degrees, voltage %s, step %s." % (panel_motor.panel_time, panel_motor.direction,
                                                                          panel_motor.max_voltage,
                                                                          panel_motor.step_max_index))
    elif (TURNTABLE_ZEROTIME[2] != localtime()[2]) and (localtime()[3] > 6) and (localtime()[3] < 21):
        panel_motor.search_best_voltage_position()
        STEPPER_LAST_STEP = panel_motor.step_max_index
        if DEBUG_ENABLED == 1:
            print("Best position: %s/%s degrees, voltage %s, step %s." % (panel_motor.panel_time, panel_motor.direction,
                                                                          panel_motor.max_voltage,
                                                                          panel_motor.step_max_index))
        if panel_motor.panel_time is None:
            if DEBUG_ENABLED == 1:
                print("Panel motor panel_time not set!")
            else:
                error_reporting("Panel motor panel_time not set!")
    else:
        # Already calibrated today, let's rotate to best position based on time from last uptime
        timediff_min = int((mktime(localtime()) - mktime(LAST_UPTIME)) / 60)
        voltage = solarpanelreader.read()
        for i in range(0, timediff_min * panel_motor.steps_for_minute):
            panel_motor.step("cw")
            STEPPER_LAST_STEP += 1
            if STEPPER_LAST_STEP >= panel_motor.max_steps_to_rotate:
                if DEBUG_ENABLED == 1:
                    print("ERROR: trying to turn over max steps to rotate!")
                error_reporting("Timely based rotation trying to turn over max steps!")
                break
        # Check that we really got best voltage
        if solarpanelreader.read() < voltage:
            if DEBUG_ENABLED == 1:
                print("Rotated too much, rotating back half of time difference!")
            for i in range(0, int(timediff_min / 2) * panel_motor.steps_for_minute):
                panel_motor.step("ccw")
                STEPPER_LAST_STEP -= 1
                if STEPPER_LAST_STEP == 1:
                    if DEBUG_ENABLED == 1:
                        print("ERROR: trying to turn below 0 steps!")
                    error_reporting("Timely based rotation trying to turn belows 0 steps!")
                    break

    try:
        mqtt_report()
    except OSError as e:
        if DEBUG_ENABLED == 1:
            print("MQTT Error %s" % e)
        else:
            pass

    LAST_BATTERY_VOLTAGE = (batteryreader.read() / 1000) / 2

    #  Deactivate seoncary circuit
    secondarycircuit(1)

    # Save parameters to the file
    runtimedata['TURNTABLE_ZEROTIME'] = TURNTABLE_ZEROTIME
    runtimedata['STEPPER_LAST_STEP'] = STEPPER_LAST_STEP
    runtimedata['LAST_BATTERY_VOLTAGE'] = (batteryreader.read() / 1000) / 2
    runtimedata['BATTERY_LOW_VOLTAGE'] = BATTERY_LOW_VOLTAGE * 2
    runtimedata['BATTERY_ADC_MULTIPLIER'] = BATTERY_ADC_MULTIPLIER
    runtimedata['LAST_UPTIME'] = localtime()
    runtimedata['LAST_TEMP'] = LAST_TEMP
    runtimedata['LAST_HUMIDITY'] = LAST_HUMIDITY
    runtimedata['LAST_PRESSURE'] = LAST_PRESSURE
    runtimedata['ULP_SLEEP_TIME'] = ULP_SLEEP_TIME
    runtimedata['KEEP_AWAKE_TIME'] = KEEP_AWAKE_TIME
    runtimedata['DEBUG_ENABLED'] = DEBUG_ENABLED

    try:
        with open('runtimeconfig.json', 'w') as f3:
            dump(runtimedata, f3)
        f3.close()

    except OSError:
        if DEBUG_ENABLED == 1:
            print("Write to runtimeconfig.json failed!")
        error_reporting("Write to runtimeconfig.json failed!")

    while n < KEEP_AWAKE_TIME:
        if DEBUG_ENABLED == 1:
            print("Going to sleep % seconds. Sleeping in %s seconds. Ctrl+C to break."
                  % (ULP_SLEEP_TIME, (KEEP_AWAKE_TIME - n)))
            sleep(1)
            n += 1
        # deepsleep(ULP_SLEEP_TIME * 1000)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise
    except MemoryError:
        reset()
