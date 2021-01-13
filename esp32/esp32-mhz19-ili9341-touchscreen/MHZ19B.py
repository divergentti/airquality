"""
Asynchronous MH-Z19 sensor reader and writer class.

Operation basics:
- Initialize the sensor with this class with import MHZ19BCO2 as CO2 and then add into main.py
    object name like co2sensor = co2.MHZ19bCO2()
-  In async main loop add asyncio.create_task(co2sensor.read_co2_loop()) and use
    object functions and variables as needed.

MH-Z19 datasheet at https://www.winsen-sensor.com/d/files/MH-Z19B.pdf

Default sensor is for 0 - 5000 ppm. Accuracy ± (50ppm+5%).
Voltage: 4.5 ~ 5.5 V DC, consumption < 20mA, max 150mA
Operating temperature -10 ~ 50 °C and humidity 0~ 90% RH.
Signlan output is 3.3V compatible. Response time T90 < 120 s.
Lifetime > 5 years.

This class uses UART (default 1), not PWM. See commands from the datasheet.

Connection:
    - ESP32 UART0 is reserved USB/REPL serialille, use either UART1 or 2, example pins 16(rx) and 17(tx).
    - sensor's tx (transmit) is connected to ESP32 rx (receive)

12.01.2021 Jari Hiltunen
"""


import machine
import utime
import uasyncio as asyncio


class MHZ19bCO2:

    # Default UART1, rx=16, tx=17, you may change these in the call
    def __init__(self, rxpin=16, txpin=17, uart=1):
        self.sensor = machine.UART(uart)
        self.sensor.init(baudrate=9600, bits=8, parity=None, stop=1, rx=rxpin, tx=txpin)
        self.zeropoint_calibrated = False
        self.co2_value = 0
        self.co2_averages = []
        self.co2_average_values = 20
        self.co2_average = 0
        self.sensor_activation_time = utime.time()
        self.value_read_time = utime.time()
        self.measuring_range = '0_5000'  # default
        self.preheat_time = 10   # shall be 180 or more
        self.read_interval = 10  # shall be 120 or more
        self.READ_COMMAND = bytearray(b'\xFF\x01\x86\x00\x00\x00\x00\x00\x79')
        self.CALIBRATE_ZEROPOINT = bytearray(b'\xFF\x01\x87\x00\x00\x00\x00\x00\x78')
        self.CALIBRATE_SPAN = bytearray(b'\xFF\x01\x88\x07\xD0\x00\x00\x00\xA0')
        self.SELF_CALIBRATION_ON = bytearray(b'\xFF\x01\x79\xA0\x00\x00\x00\x00\xE6')
        self.SELF_CALIBRATION_OFF = bytearray(b'\xFF\x01\x79\x00\x00\x00\x00\x00\x86')
        self.MEASURING_RANGE_0_2000PPM = bytearray(b'\xFF\x01\x99\x00\x00\x00\x07\xD0\x8F')
        self.MEASURING_RANGE_0_5000PPM = bytearray(b'\xFF\x01\x99\x00\x00\x00\x13\x88\xCB')
        self.MEASURING_RANGE_0_10000PPM = bytearray(b'\xFF\x01\x99\x00\x00\x00\x27\x10\x2F')

    async def writer(self, data):
        port = asyncio.StreamWriter(self.sensor, {})
        port.write(data)
        await port.drain()    # Transmit begins
        await asyncio.sleep(2)   # Minimum read frequency 2 seconds

    async def reader(self, chars):
        port = asyncio.StreamReader(self.sensor)
        data = await port.readexactly(chars)
        return data

    async def read_co2_loop(self):
        while True:
            if (utime.time() - self.sensor_activation_time) < self.preheat_time:
                #  By the datasheet, preheat shall be 3 minutes
                print("Preheating ... wait")
                await asyncio.sleep(1)
            elif (utime.time() - self.value_read_time) > self.read_interval:
                #  Read values in 2 min frequency
                print("Reading value, wait...")
                try:
                    await self.writer(self.READ_COMMAND)
                    readbuffer = bytearray(await self.reader(9))
                    if readbuffer[0] == 0xff and self._calculate_crc(readbuffer) == readbuffer[8]:
                        self.co2_value = self._data_to_co2_level(readbuffer)
                        self.calculate_average(self.co2_value)
                        self.value_read_time = utime.time()
                except TypeError as e:
                    print("Error %s", e)
                    pass
            await asyncio.sleep(self.read_interval)

    def calculate_average(self, co2):
        self.co2_averages.append(co2)
        self.co2_average = (sum(self.co2_averages) / len(self.co2_averages))
        #  read 20 values, delete oldest
        if len(self.co2_averages) == self.co2_average_values:
            self.co2_averages.pop(0)

    def calibrate_zeropoint(self):
        if utime.time() - self.sensor_activation_time > (20 * 60):
            self.writer(self.CALIBRATE_ZEROPOINT)
            self.zeropoint_calibrated = True
        else:
            print("Prior calibration sensor must be heated at least 20 minutes!")

    def calibrate_span(self):
        if self.zeropoint_calibrated is True:
            self.writer(self.CALIBRATE_SPAN)
        else:
            print("Zeropoint must be calibrated first!")

    def selfcalibration_on(self):
        self.writer(self.SELF_CALIBRATION_ON)

    def selfcalibration_off(self):
        self.writer(self.SELF_CALIBRATION_OFF)

    def measuring_range_0_2000_ppm(self):
        self.writer(self.MEASURING_RANGE_0_2000PPM)
        self.measuring_range = '0_2000'

    def measuring_range_0_5000_ppm(self):
        self.writer(self.MEASURING_RANGE_0_5000PPM)
        self.measuring_range = '0_5000'

    def measuring_range_0_10000_ppm(self):
        self.writer(self.MEASURING_RANGE_0_10000PPM)
        self.measuring_range = '0_10000'

    @staticmethod
    # Borrowed from https://github.com/dr-mod/co2-monitoring-station/blob/master/mhz19b.py
    def _calculate_crc(readbuffer):
        if len(readbuffer) != 9:
            return None
        crc = sum(readbuffer[1:8])
        return (~(crc & 0xff) & 0xff) + 1

    @staticmethod
    def _data_to_co2_level(data):
        return data[2] << 8 | data[3]
