from lib import adafruit_ina219
from ucollections import OrderedDict
from phew import logging
from enviro.constants import I2C_ADDR_INA219
from enviro.helpers import get_battery_percent


def get_readings(i2c, address=I2C_ADDR_INA219):
    ina = adafruit_ina219.INA219(i2c, address)
    logging.info(f"  - LTR390 initialized")
    volts = ina.bus_voltage
    readings = OrderedDict(
        {
            "battery_voltage": volts,
            "battery_percent": get_battery_percent(volts)
        }
    )
    logging.debug(f"> battery voltage: {readings['battery_voltage']}, percent: {readings['battery_percent']}")
    return readings
