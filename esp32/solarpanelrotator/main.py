"""
For ESP32-Wrover or ESP32-Wroom in ULP (Ultra Low Power) mode.

Operation: fist time rotates full round and If SOUTH_STEP is not set, turns solar panel towards the sun and measures
with BME280 temperature, humidity and pressure and sends information to the mqtt broker and then sleeps.

If SOUTH_STEP is set, use information for direction stepping.

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

If the code breaks, execute f4.close() and download boottime.log

"""

import Steppermotor
from machine import I2C, Pin, ADC, reset, deepsleep, reset_cause
from utime import sleep, localtime, mktime, ticks_ms
import ntptime
import gc
from umqttsimple import MQTTClient
import network
from json import load, dump
import BME280_float as BmE
from Suntime import Sun
import os

# Boottime logger
try:
    f4 = open('boottime.log', "r")
    exists = True
    f4.close()
except OSError:
    exists = False

if exists is False:
    f4 = open('boottime.log', 'w')
    f4.write("----------------\n"
             "Boottime Logger\n"
             "New file started\n"
             "----------------\n")
else:
    try:
        os.remove('boottime.old')
    except OSError:
        pass
    os.rename('boottime.log', 'boottime.old')
    f4 = open('boottime.log', 'w')
    f4.write("----------------\n"
             "Boottime Logger\n"
             "Old log renamed to old\n"
             "New file started\n"
             "----------------\n")

f4.write("Previous boot reason %s \n" % reset_cause())

try:
    f = open('parameters.py', "r")
    from parameters import SSID1, SSID2, PASSWORD1, PASSWORD2, MQTT_SERVER, MQTT_PASSWORD, MQTT_USER, MQTT_PORT, \
        CLIENT_ID, BATTERY_ADC_PIN, TOPIC_ERRORS, STEPPER1_PIN1, STEPPER1_PIN2, STEPPER1_PIN3, STEPPER1_PIN4, \
        STEPPER1_DELAY, MICROSWITCH_PIN, SOLARPANEL_ADC_PIN, TOPIC_TEMP, TOPIC_PRESSURE, TOPIC_HUMIDITY, \
        TOPIC_BATTERY_VOLTAGE, I2C_SCL_PIN, I2C_SDA_PIN, SECONDARY_ACTIVATION_PIN
    f.close()
except OSError:  # open failed
    print("parameter.py-file missing! Can not continue!")
    f4.write("parameter.py-file missing! Can not continue!\n")
    f4.close()
    raise

f4.write("Parameter.py loaded OK\n")

try:
    f2 = open('runtimeconfig.json', 'r')
    with open('runtimeconfig.json') as config_file:
        runtimedata = load(config_file)
        f2.close()
        TURNTABLE_ZEROTIME = runtimedata['TURNTABLE_ZEROTIME']
        STEPPER_LAST_STEP = runtimedata['STEPPER_LAST_STEP']
        LAST_BATTERY_VOLTAGE = runtimedata['LAST_BATTERY_VOLTAGE']
        BATTERY_LOW_VOLTAGE = runtimedata['BATTERY_LOW_VOLTAGE']
        BATTERY_ADC_MULTIPLIER = runtimedata['BATTERY_ADC_MULTIPLIER']
        LAST_UPTIME = runtimedata['LAST_UPTIME']
        LAST_TEMP = runtimedata['LAST_TEMP']
        LAST_HUMIDITY = runtimedata['LAST_HUMIDITY']
        LAST_PRESSURE = runtimedata['LAST_PRESSURE']
        ULP_SLEEP_TIME = runtimedata['ULP_SLEEP_TIME']
        KEEP_AWAKE_TIME = runtimedata['KEEP_AWAKE_TIME']
        DEBUG_ENABLED = runtimedata['DEBUG_ENABLED']
        SOUTH_STEP = runtimedata['SOUTH_STEP']
        TIMEZONE_DIFFERENCE = runtimedata['TIMEZONE_DIFFERENCE']
        LONGITUDE = runtimedata['LONGITUDE']
        LATITUDE = runtimedata['LATITUDE']
        MICROSWITCH_STEPS = runtimedata['MICROSWITCH_STEPS']
except OSError:
    print("Runtime parameters missing. Can not continue!")
    f4.write("Runtime parameters missing. Can not continue!\n")
    f4.close()
    raise

f4.write("runtimeconfig.json loaded OK\n")


''' Globals '''
dst_on = None
daytime = False


class StepperMotor(object):

    """ ULN2003-based control, half steps. Gear ratio 0.5 : 1 """

    def __init__(self, in1, in2, in3, in4, indelay):
        self.motor = Steppermotor.create(Pin(in1, Pin.OUT), Pin(in2, Pin.OUT), Pin(in3, Pin.OUT),
                                         Pin(in4, Pin.OUT), delay=indelay)
        self.stepdelay = indelay
        self.solar_voltage = None
        self.battery_voltage = None
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
        if MICROSWITCH_STEPS is None:
            self.microswitch_steps = 0
        else:
            self.microswitch_steps = MICROSWITCH_STEPS
        if STEPPER_LAST_STEP is not None:
            self.steps_taken = STEPPER_LAST_STEP
        else:
            self.steps_taken = 0
        self.southstep = SOUTH_STEP
        if self.southstep is not None:
            self.sw = self.southstep + (45 * self.steps_for_minute)
            if self.sw > self.max_steps_to_rotate:
                self.sw = self. max_steps_to_rotate
            self.west = self.southstep + (90 * self.steps_for_minute)
            if self.west > self.max_steps_to_rotate:
                self.west = self.max_steps_to_rotate
            self.se = self.southstep - (45 * self.steps_for_minute)
            if self.se < 1:
                self.se = 1
            self.east = self.southstep - (90 * self.steps_for_minute)
            if self.east < 1:
                self.east = 1
        else:
            self.sw = None
            self.west = None
            self.se = None
            self.east = None

    def turn_to_south_step(self):
        if self.southstep is not None:
            self.turn_to_limiter()
            for i in range(1, self.southstep):
                self.step("cw")

    def step(self, direction, overrideswitch=False):
        if direction == "cw":
            turn = -1
        elif direction == "ccw":
            turn = 1
        else:
            return False

        if DEBUG_ENABLED == 1:
            print('[Step#: %s Volts: %s]\r' % (self.steps_taken, self.solar_voltage), end="")

        if limiter_switch.value() == 0:
            self.steps_taken = 0

        if (overrideswitch is False) and (limiter_switch.value() == 1) and \
                (self.steps_taken <= self.max_steps_to_rotate):
            # switch = 1 means switch is open
            self.table_turning = True
            try:
                self.motor.step(1, turn)
            except OSError as ex:
                self.table_turning = False
                if DEBUG_ENABLED == 1:
                    print('ERROR %s stepping %s:' % (ex, direction))
            if turn == -1:
                self.steps_taken += 1
            else:
                self.steps_taken -= 1
            self.table_turning = False

        if (overrideswitch is True) and (self.steps_taken <= self.max_steps_to_rotate):
            self.table_turning = True
            try:
                self.motor.step(1, turn)
            except OSError as ex:
                self.table_turning = False
                if DEBUG_ENABLED == 1:
                    print('ERROR %s stepping %s:' % (ex, direction))
            if turn == -1:
                self.steps_taken += 1
            else:
                self.steps_taken -= 1
            self.table_turning = False

    def turn_to_limiter(self, keepclosed=False):
        global STEPPER_LAST_STEP
        global MICROSWITCH_STEPS
        if DEBUG_ENABLED == 1:
            print("Starting rotation counterclockwise until limiter switch turns off...")
        starttime = ticks_ms()
        # Maximum time to turn full round is about 22 seconds.
        while limiter_switch.value() == 1 and ((ticks_ms() - starttime) < 22000):
            self.step("ccw")
        self.microswitch_steps = 0
        if DEBUG_ENABLED == 1:
            print("Switch on, taking a few steps back to open the switch...")
        if keepclosed is False:
            # Take a few steps back to open the switch
            while limiter_switch.value() == 0:
                self.step("cw", overrideswitch=True)
                self.microswitch_steps += 1
        self.table_turning = False
        STEPPER_LAST_STEP = self.microswitch_steps
        MICROSWITCH_STEPS = self.microswitch_steps

    def search_best_voltage_position(self):
        global TURNTABLE_ZEROTIME
        if DEBUG_ENABLED == 1:
            print("Finding highest voltage direction for the solar panel. Wait.")
        self.turn_to_limiter()
        #  Look steps clockwise
        if DEBUG_ENABLED == 1:
            print("Turning panel clockwise %s steps" % self.max_steps_to_rotate)
        for i in range(1, self.max_steps_to_rotate):
            self.step("cw")
            self.solar_voltage = ((solarpanelreader.read() / 1000) * 2)  # due to voltage splitter
            if self.solar_voltage is not None:
                try:
                    self.steps_voltages.append(self.solar_voltage)
                except MemoryError:
                    gc.collect()
                gc.collect()
        if len(self.steps_voltages) < self.max_steps_to_rotate - 1:
            if DEBUG_ENABLED == 1:
                print("Some values missing! Should be %s, is %s" % (self.max_steps_to_rotate, len(self.steps_voltages)))
            error_reporting("Some values missing! Should be %s, is %s" % (self.max_steps_to_rotate,
                                                                          len(self.steps_voltages)))
            f4.write("Some values missing! Should be %s, is %s\n" % (str(self.max_steps_to_rotate),
                                                                     str(len(self.steps_voltages))))
            return False
        #  Now we have voltages for each step, check which one has highest voltage. First occurence.
        self.max_voltage = max(self.steps_voltages)
        self.step_max_index = self.steps_voltages.index(max(self.steps_voltages))
        self.panel_time = localtime()
        self.direction = (int(self.panel_time[3] * 60) + int(self.panel_time[4])) * self.degrees_minute
        """ Maximum voltage value found. Turn to maximum"""
        if DEBUG_ENABLED == 1:
            print("Rotating back to maximum %s steps" % (self.max_steps_to_rotate - self.step_max_index))
        f4.write("Rotating back to maximum %s steps\n" % str((self.max_steps_to_rotate - self.step_max_index)))
        for i in range(1, (self.max_steps_to_rotate - self.step_max_index)):
            self.step("ccw")
        TURNTABLE_ZEROTIME = localtime()
        #  The sun shall be about south at LOCAL 12:00 winter time (summer +1h)
        if localtime()[3] == 12:
            self.southstep = self.steps_taken
            if DEBUG_ENABLED == 1:
                print("South step %s set." % self.southstep)
            f4.write("South step %s set.\n" % str(self.southstep))
        self.table_turning = False


def resolve_dst_and_set_time():
    global TIMEZONE_DIFFERENCE
    global dst_on
    # This is most stupid thing what humans can do!
    # Rules for Finland: DST ON: March last Sunday at 03:00 + 1h, DST OFF: October last Sunday at 04:00 - 1h
    # Sets localtime to DST localtime
    now = mktime(localtime())

    try:
        now = ntptime.time()
    except OSError as e:
        if DEBUG_ENABLED == 1:
            print("NTP time not set! Error %s" % e)
        f4.write("NTP time not set! Error %s\n" % e)

    (year, month, mdate, hour, minute, second, wday, yday) = localtime(now)

    if year < 2021:
        if DEBUG_ENABLED == 1:
            print("Time not set correctly!")
        f4.write("Time not set correctly!\n")

    dstend = mktime((year, 10, (31 - (int(5 * year / 4 + 1)) % 7), 4, 0, 0, 0, 6, 0))
    dstbegin = mktime((year, 3, (31 - (int(5 * year / 4 + 4)) % 7), 3, 0, 0, 0, 6, 0))

    if TIMEZONE_DIFFERENCE >= 0:
        if (now > dstbegin) and (now < dstend):
            dst_on = True
            ntptime.NTP_DELTA = 3155673600 - ((TIMEZONE_DIFFERENCE + 1) * 3600)
        else:
            dst_on = False
            ntptime.NTP_DELTA = 3155673600 - (TIMEZONE_DIFFERENCE * 3600)
    else:
        if (now > dstend) and (now < dstbegin):
            dst_on = False
            ntptime.NTP_DELTA = 3155673600 - (TIMEZONE_DIFFERENCE * 3600)
        else:
            dst_on = True
            ntptime.NTP_DELTA = 3155673600 - ((TIMEZONE_DIFFERENCE + 1) * 3600)
    try:
        ntptime.settime()
    except OverflowError:
        gc.collect()
        try:
            ntptime.settime()
        except OverflowError:
            pass
    except OSError as e:
        error_reporting("npttime.settime() error %s " % e)
        f4.write("npttime.settime() error %s\n" % e)


def resolve_date_local_format():
    # Finland
    (year, month, mdate, hour, minute, second, wday, yday) = localtime()
    date = "%s.%s.%s time %s:%s:%s" % (mdate, month, year, "{:02d}".format(hour),
                                       "{:02d}".format(minute), "{:02d}".format(second))
    return date


def error_reporting(error):
    f4.write(error + "\n")
    if network.WLAN(network.STA_IF).config('essid') != '':
        # error message: date + time;uptime;devicename;ip;error;free mem
        errormessage = str(resolve_date_local_format()) + ";" + str(ticks_ms()) + ";" \
            + str(CLIENT_ID) + ";" + str(network.WLAN(network.STA_IF).ifconfig()) + ";" + str(error) +\
            ";" + str(gc.mem_free())
        client.publish(TOPIC_ERRORS, str(errormessage), retain=False)
    else:
        if DEBUG_ENABLED == 1:
            print("Network down! Can not publish error message! Boot in 10s.")
        f4.write("Network down! Can not publish error message! Boot in 10s.\n")
        f4.close()
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
        if batteryreader.read() > 0:
            client.publish(TOPIC_BATTERY_VOLTAGE, str((batteryreader.read() / 1000) * 2), retain=0, qos=0)

    else:
        if DEBUG_ENABLED == 1:
            print("Network down! Can not publish to MQTT! Boot in 10s.")
        f4.write("Network down! Can not publish to MQTT! Boot in 10s.\n")
        f4.close()
        sleep(10)
        reset()


gc.collect()

resolve_dst_and_set_time()

if dst_on is True:
    # Sun rise or set calculation. Timezone drift from the UTC!
    sun = Sun(LATITUDE, LONGITUDE, TIMEZONE_DIFFERENCE + 1)
else:
    sun = Sun(LATITUDE, LONGITUDE, TIMEZONE_DIFFERENCE)

sunrise = sun.get_sunrise_time() + (00, 00, 00)
sunset = sun.get_sunset_time() + (00, 00, 00)
timenowsec = (mktime(localtime()))

if (timenowsec > mktime(sunrise)) and (timenowsec < mktime(sunset)):
    daytime = True
else:
    daytime = False

if DEBUG_ENABLED == 1:
    print("Sunrise today %s, sunset today %s, now is daytime %s" % (sunrise, sunset, daytime))
f4.write("Sunrise today %s, sunset today %s, now is daytime %s\n" % (str(sunrise), str(sunset), str(daytime)))


# Secondary circuit setup
secondarycircuit = Pin(SECONDARY_ACTIVATION_PIN, mode=Pin.OPEN_DRAIN, pull=-1)
f4.write("Secondary circuit initialized\n")
#  Activate secondary circuit. Sensors will start measuring and motor can turn.
secondarycircuit(0)
sleep(1)

""" Global objects """
batteryreader = ADC(Pin(BATTERY_ADC_PIN))
# Attennuation below 1 volts 11 db
batteryreader.atten(ADC.ATTN_11DB)
f4.write("Batteryreader circuit initialized\n")
solarpanelreader = ADC(Pin(SOLARPANEL_ADC_PIN))
solarpanelreader.atten(ADC.ATTN_11DB)
f4.write("Solarpanel circuit initialized\n")

#  First initialize limiter_switch object, then panel motor
limiter_switch = Pin(MICROSWITCH_PIN, Pin.IN, Pin.PULL_UP)
f4.write("Limiter switch circuit initialized\n")

try:
    panel_motor = StepperMotor(STEPPER1_PIN1, STEPPER1_PIN2, STEPPER1_PIN3, STEPPER1_PIN4, STEPPER1_DELAY)
except OSError as e:
    if DEBUG_ENABLED == 1:
        print("Check StepperMotor pins!!")
    f4.write("Check StepperMotor pins!!\n")
    f4.close()
    raise

f4.write("Panel motor initialized\n")

i2c = I2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN))
f4.write("I2C initialized\n")

try:
    bmes = BmE.BME280(i2c=i2c)
except OSError as e:
    print("Check BME sensor I2C pins!")
    f4.write("Error: Check BME sensor I2C pins!\n")
    f4.close()
    raise

f4.write("BME280 initialized\n")

# MQTT
client = MQTTClient(CLIENT_ID, MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD)
f4.write("MQTTClient object initialized\n")


def main():
    global LAST_UPTIME
    global LAST_BATTERY_VOLTAGE
    global STEPPER_LAST_STEP
    global ULP_SLEEP_TIME
    global SOUTH_STEP
    global TURNTABLE_ZEROTIME

    # TRY - EXCEPT catch during main() init

    battery_voltage = (batteryreader.read() / 1000) * 2
    if battery_voltage < BATTERY_LOW_VOLTAGE:
        if DEBUG_ENABLED == 1:
            print("Battery voltage %s too low!" % battery_voltage)
        error_reporting("Battery voltage %s too low!" % battery_voltage)
        f4.write("Battery voltage %s too low!\n" % str(battery_voltage))

    f4.write("Free memory %s\n" % str(gc.mem_free()))
    gc.collect()

    client.connect()

    f4.write("MQTT Initialized\n")

    f4.write("Daytime is %s, starting operations...\n" % daytime)

    #  Find best step and direction for the solar panel. Do once when boot, then if needed
    if (daytime is True) and (TURNTABLE_ZEROTIME is None):
        f4.write("%s: TURNTABLE_ZEROTIME is None, first time turns\n" % str(localtime()))
        panel_motor.search_best_voltage_position()
        STEPPER_LAST_STEP = panel_motor.steps_taken
        if LAST_UPTIME is None:
            LAST_UPTIME = localtime()
        if DEBUG_ENABLED == 1:
            print("Best position: %s/%s degrees, voltage %s, step %s." % (panel_motor.panel_time,
                                                                          panel_motor.direction,
                                                                          panel_motor.max_voltage,
                                                                          panel_motor.step_max_index))
        f4.write(("Best position: %s/%s degrees, voltage %s, step %s.\n" % (panel_motor.panel_time,
                                                                            panel_motor.direction,
                                                                            panel_motor.max_voltage,
                                                                            panel_motor.step_max_index)))

        # Midday checkup for south position
    if (daytime is True) and (SOUTH_STEP is None) and (TURNTABLE_ZEROTIME is not None) and (localtime()[3] == 12):
        f4.write("%s: Southsteps setting\n" % str(localtime()))
        panel_motor.search_best_voltage_position()
        STEPPER_LAST_STEP = panel_motor.steps_taken
        SOUTH_STEP = panel_motor.southstep
        if LAST_UPTIME is None:
            LAST_UPTIME = localtime()
        if DEBUG_ENABLED == 1:
            print("Best position: %s/%s degrees, voltage %s, step %s." % (panel_motor.panel_time,
                                                                          panel_motor.direction,
                                                                          panel_motor.max_voltage,
                                                                          panel_motor.step_max_index))
        f4.write(("Best position: %s/%s degrees, voltage %s, step %s.\n" % (panel_motor.panel_time,
                                                                            panel_motor.direction,
                                                                            panel_motor.max_voltage,
                                                                            panel_motor.step_max_index)))

    #  Normal rotation same day
    if (daytime is True) and (TURNTABLE_ZEROTIME is not None) and (localtime()[2] == LAST_UPTIME[2]):
        f4.write("%s: Normal rotation begings\n" % str(localtime()))
        timediff_min = int((mktime(localtime()) - mktime(LAST_UPTIME)) / 60)
        voltage = solarpanelreader.read()
        LAST_UPTIME = localtime()
        for i in range(1, timediff_min * panel_motor.steps_for_minute):
            panel_motor.step("cw")
        # Check that we really got best voltage
        if (solarpanelreader.read() < voltage) and (panel_motor.steps_taken > STEPPER_LAST_STEP):
            if DEBUG_ENABLED == 1:
                print("Rotated too much, rotating back half of time difference!")
            f4.write("Rotated too much, rotating back half of time difference!\n")
            for i in range(1, int(timediff_min / 2) * panel_motor.steps_for_minute):
                panel_motor.step("ccw")

    # Normal rotation next day morning
    if (daytime is True) and (TURNTABLE_ZEROTIME is not None) and (localtime()[2] != LAST_UPTIME[2]):
        voltage = solarpanelreader.read()
        LAST_UPTIME = localtime()
        if panel_motor.east is not None:
            # Turn to east, panel shall be in the limiter already
            for i in range(1, panel_motor.east):
                panel_motor.step("cw")
        else:
            panel_motor.turn_to_limiter()
        # Check that we really got best voltage
        if (solarpanelreader.read() < voltage) and (panel_motor.steps_taken > STEPPER_LAST_STEP):
            if DEBUG_ENABLED == 1:
                print("Rotated too much, rotating back half of east position!")
            f4.write("Rotated too much, rotating back half of east position!\n")
            for i in range(1, int(panel_motor.east / 2)):
                panel_motor.step("ccw")

    # Calibrate again once a week
    if (daytime is True) and (localtime()[2] - TURNTABLE_ZEROTIME[2] >= 7) and (localtime()[3] == 12):
        f4.write("%s: Calibration begins\n" % str(localtime()))
        panel_motor.search_best_voltage_position()
        STEPPER_LAST_STEP = panel_motor.steps_taken
        SOUTH_STEP = panel_motor.southstep
        TURNTABLE_ZEROTIME = localtime()
        if LAST_UPTIME is None:
            LAST_UPTIME = localtime()
        if DEBUG_ENABLED == 1:
            print("Best position: %s/%s degrees, voltage %s, step %s." % (panel_motor.panel_time,
                                                                          panel_motor.direction,
                                                                          panel_motor.max_voltage,
                                                                          panel_motor.step_max_index))
        f4.write("Best position: %s/%s degrees, voltage %s, step %s.\n" % (panel_motor.panel_time,
                                                                           panel_motor.direction,
                                                                           panel_motor.max_voltage,
                                                                           panel_motor.step_max_index))
    # Rotate turntable to limiter for night
    if daytime is False:
        f4.write("Nightime, turn to limiter\n")
        # Do not update LAST_UPTIME!
        if STEPPER_LAST_STEP > MICROSWITCH_STEPS:
            panel_motor.turn_to_limiter()
        STEPPER_LAST_STEP = panel_motor.steps_taken

    f4.write("Begin mqtt reporting\n")
    mqtt_report()

    f4.write("Begin runtimedata save\n")
    # Save parameters to the file
    runtimedata['TURNTABLE_ZEROTIME'] = TURNTABLE_ZEROTIME
    runtimedata['STEPPER_LAST_STEP'] = panel_motor.steps_taken
    runtimedata['LAST_BATTERY_VOLTAGE'] = (batteryreader.read() / 1000) * 2
    runtimedata['BATTERY_LOW_VOLTAGE'] = BATTERY_LOW_VOLTAGE
    runtimedata['BATTERY_ADC_MULTIPLIER'] = BATTERY_ADC_MULTIPLIER
    runtimedata['LAST_UPTIME'] = LAST_UPTIME
    runtimedata['LAST_TEMP'] = LAST_TEMP
    runtimedata['LAST_HUMIDITY'] = LAST_HUMIDITY
    runtimedata['LAST_PRESSURE'] = LAST_PRESSURE
    runtimedata['ULP_SLEEP_TIME'] = ULP_SLEEP_TIME
    runtimedata['KEEP_AWAKE_TIME'] = KEEP_AWAKE_TIME
    runtimedata['DEBUG_ENABLED'] = DEBUG_ENABLED
    runtimedata['SOUTH_STEP'] = SOUTH_STEP
    runtimedata['TIMEZONE_DIFFERENCE'] = TIMEZONE_DIFFERENCE
    runtimedata['LONGITUDE'] = LONGITUDE
    runtimedata['LATITUDE'] = LATITUDE
    runtimedata['MICROSWITCH_STEPS'] = MICROSWITCH_STEPS

    with open('runtimeconfig.json', 'w') as f3:
        dump(runtimedata, f3)
    f3.close()
    f4.write("Runtimeconfig save complete\n")

    #  Deactivate seoncary circuit
    secondarycircuit(1)

    # Drop WiFi connection, reconnect at boot.py
    f4.write("Disconnect WiFi\n")
    if network.WLAN(network.STA_IF).config('essid') != '':
        network.WLAN(network.STA_IF).disconnect()

    # Keep system up in case WebREPL is needed
    n = 0
    f4.write("Wait %s seconds\n" % str(KEEP_AWAKE_TIME))
    while n < KEEP_AWAKE_TIME:
        if DEBUG_ENABLED == 1:
            print("Going to sleep % seconds. Sleeping in %s seconds. Ctrl+C to break."
                  % (ULP_SLEEP_TIME, (KEEP_AWAKE_TIME - n)))
        sleep(1)
        n += 1

    # Avoid skipping midday checkup, wake once before midday
    (year, month, mdate, hour, minute, second, wday, yday) = localtime()
    target_time = (year, month, mdate, 12, 0, second, wday, yday)
    seconds_to_midday = mktime(target_time) - mktime(localtime())
    if (ULP_SLEEP_TIME >= 3600) and (seconds_to_midday > 0) and (seconds_to_midday <= 3600):
        f4.write("ULP Sleep less than 3600\n")
        f4.close()
        deepsleep(3500 * 1000)
    else:
        f4.write("ULP Sleep normal %s seconds\n" % str(ULP_SLEEP_TIME))
        f4.close()
        deepsleep(ULP_SLEEP_TIME * 1000)


if __name__ == "__main__":
    f4.write("Execute main\n")
    try:
        main()
    except Exception as e:
        f4.write("Exception %s" % e)
        if type(e).__name__ == "MQTTException":
            if DEBUG_ENABLED == 1:
                print("** ERROR: Check MQTT server connection info, username and password! **")
            error_reporting("ERROR: Check MQTT server connection info, username and password!")
            f4.close()
            raise
        elif type(e).__name__ == "OSError":
            if DEBUG_ENABLED == 1:
                print("OSError %s! Booting in 10 seconds." % e)
            f4.close()
            error_reporting("OSError %s" % e)
            sleep(10)
            reset()
        elif type(e).__name__ == "MemoryError":
            if DEBUG_ENABLED == 1:
                print("Memory Error %s! Booting in 10 seconds." % e)
            f4.close()
            sleep(10)
            reset()
        elif type(e).__name__ == "KeyboardInterrupt":
            f4.close()
            raise
