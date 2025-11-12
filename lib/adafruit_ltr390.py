# lib/ltr390_mpy.py
# MicroPython driver simplificado para LTR390 (Adafruit Qwiic board)
# Compatível com RPi Pico W

import time
from machine import I2C

LTR390_I2CADDR_DEFAULT = 0x53

# Registradores principais
REG_MAIN_CTRL = 0x00
REG_MEAS_RATE = 0x04
REG_GAIN = 0x05
REG_PART_ID = 0x06
REG_ALS_DATA = 0x0D
REG_UVS_DATA = 0x10
REG_STATUS = 0x07


class LTR390:
    def __init__(self, i2c, address=LTR390_I2CADDR_DEFAULT):
        self.i2c = i2c
        self.address = address
        part_id = self._read8(REG_PART_ID)
        if part_id != 0xB2:
            raise RuntimeError("LTR390 not found (ID=%02X)" % part_id)
        self._write8(REG_MAIN_CTRL, 0x02)  # modo ALS
        time.sleep_ms(100)
        self.set_gain(3)
        self.set_rate(2)

    def _read8(self, reg):
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]

    def _write8(self, reg, val):
        self.i2c.writeto_mem(self.address, reg, bytes([val]))

    def _read24(self, reg):
        data = self.i2c.readfrom_mem(self.address, reg, 3)
        return data[0] | (data[1] << 8) | (data[2] << 16)

    def set_gain(self, gain=3):
        # 0=1x,1=3x,2=6x,3=9x,4=18x
        self._write8(REG_GAIN, gain)

    def set_rate(self, rate=2):
        # 0=25ms,1=50ms,2=100ms,3=200ms,4=500ms,5=1000ms,6=2000ms
        self._write8(REG_MEAS_RATE, rate)

    def read_uvs(self):
        self._write8(REG_MAIN_CTRL, 0x0A)  # modo UV
        time.sleep_ms(100)
        val = self._read24(REG_UVS_DATA)
        return val

    def read_als(self):
        self._write8(REG_MAIN_CTRL, 0x02)  # modo luz ambiente
        time.sleep_ms(100)
        val = self._read24(REG_ALS_DATA)
        return val
