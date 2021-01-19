"""
  19.01.2020: Jari Hiltunen

  Original https://github.com/pkucmus/micropython-pms7003/blob/master/pms7003.py
  Modified for asyncronous StreamReader  16.01.2020 by Divergentti / Jari Hiltunen

"""

from machine import UART
import struct
import utime
import uasyncio as asyncio


class PSensorPMS7003:

    START_BYTE_1 = 0x42
    START_BYTE_2 = 0x4d
    PMS_FRAME_LENGTH = 0
    PMS_PM1_0 = 1
    PMS_PM2_5 = 2
    PMS_PM10_0 = 3
    PMS_PM1_0_ATM = 4
    PMS_PM2_5_ATM = 5
    PMS_PM10_0_ATM = 6
    PMS_PCNT_0_3 = 7
    PMS_PCNT_0_5 = 8
    PMS_PCNT_1_0 = 9
    PMS_PCNT_2_5 = 10
    PMS_PCNT_5_0 = 11
    PMS_PCNT_10_0 = 12
    PMS_VERSION = 13
    PMS_ERROR = 14
    PMS_CHECKSUM = 15

    #  Default UART1, rx=32, tx=33. Don't use UART0 if you want to use REPL!
    def __init__(self, rxpin=32, txpin=33, uart=1):
        self.sensor = UART(uart, baudrate=9600, bits=8, parity=None, stop=1, rx=rxpin, tx=txpin)
        self.pms_dictionary = None
        self.startup_time = utime.time()   # TODO: implement 30 s wait prior to reading

    async def reader(self, chars):
        port = asyncio.StreamReader(self.sensor)
        data = await port.readexactly(chars)
        return data

    @staticmethod
    def _assert_byte(byte, expected):
        if byte is None or len(byte) < 1 or ord(byte) != expected:
            return False
        return True

    async def read_async_loop(self):

        while True:

            first_byte = await self.reader(1)
            if not self._assert_byte(first_byte, PSensorPMS7003.START_BYTE_1):
                continue

            second_byte = await self.reader(1)
            if not self._assert_byte(second_byte, PSensorPMS7003.START_BYTE_2):
                continue

            # we are reading 30 bytes left
            read_bytes = await self.reader(30)
            if len(read_bytes) < 30:
                continue

            data = struct.unpack('!HHHHHHHHHHHHHBBH', read_bytes)

            checksum = PSensorPMS7003.START_BYTE_1 + PSensorPMS7003.START_BYTE_2
            checksum += sum(read_bytes[:28])

            if checksum != data[PSensorPMS7003.PMS_CHECKSUM]:
                continue

            self.pms_dictionary = {
                'FRAME_LENGTH': data[PSensorPMS7003.PMS_FRAME_LENGTH],
                'PM1_0': data[PSensorPMS7003.PMS_PM1_0],
                'PM2_5': data[PSensorPMS7003.PMS_PM2_5],
                'PM10_0': data[PSensorPMS7003.PMS_PM10_0],
                'PM1_0_ATM': data[PSensorPMS7003.PMS_PM1_0_ATM],
                'PM2_5_ATM': data[PSensorPMS7003.PMS_PM2_5_ATM],
                'PM10_0_ATM': data[PSensorPMS7003.PMS_PM10_0_ATM],
                'PCNT_0_3': data[PSensorPMS7003.PMS_PCNT_0_3],
                'PCNT_0_5': data[PSensorPMS7003.PMS_PCNT_0_5],
                'PCNT_1_0': data[PSensorPMS7003.PMS_PCNT_1_0],
                'PCNT_2_5': data[PSensorPMS7003.PMS_PCNT_2_5],
                'PCNT_5_0': data[PSensorPMS7003.PMS_PCNT_5_0],
                'PCNT_10_0': data[PSensorPMS7003.PMS_PCNT_10_0],
                'VERSION': data[PSensorPMS7003.PMS_VERSION],
                'ERROR': data[PSensorPMS7003.PMS_ERROR],
                'CHECKSUM': data[PSensorPMS7003.PMS_CHECKSUM], }
