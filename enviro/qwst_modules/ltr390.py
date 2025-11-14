from lib import adafruit_ltr390
from ucollections import OrderedDict
from phew import logging


def get_readings(i2c, address):
    uv_sensor = adafruit_ltr390.LTR390(i2c)
    logging.debug(f"  - LTR390 initialized")
    uv = uv_sensor.read_uvs()
    readings = OrderedDict(
        {
            "uv_raw": uv,
            "als_raw": uv_sensor.read_als(),
            "uv_index": uv / 2300.0,
        }
    )
    logging.debug(
        f"  - uv readings - uv: {readings['uv_raw']}, als: {readings['als_raw']}, uv index: {readings['uv_index']}"
    )
    return readings
