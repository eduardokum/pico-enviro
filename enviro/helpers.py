from enviro.constants import *
import machine, math, os, time, utime
from phew import logging
import config

ADC_VOLT_CONVERSION = 3.3 / 65535  # fator de conversão ADC → volts
ADC_CHANNEL = 3  # canal 3 = VSYS/3
VOLTAGE_SAMPLES = 10  # quantidade de amostras para média
BATTERY_CURVE = [
    (4.20, 100),
    (4.15, 95),
    (4.10, 90),
    (4.05, 85),
    (4.00, 80),
    (3.95, 75),
    (3.90, 70),
    (3.85, 65),
    (3.80, 60),
    (3.75, 55),
    (3.70, 50),
    (3.65, 40),
    (3.60, 30),
    (3.55, 20),
    (3.45, 10),
    (3.30, 5),
    (3.00, 0),
]

try:
    import config  # fails to import (missing/corrupt) go into provisioning

    VOLTAGE_CALIBRATION_FACTOR = config.voltage_calibration_factor
except Exception as e:
    VOLTAGE_CALIBRATION_FACTOR = 1.000


# miscellany
# ===========================================================================
def datetime_string():
    dt = machine.RTC().datetime()
    return "{0:04d}-{1:02d}-{2:02d}T{4:02d}:{5:02d}:{6:02d}Z".format(*dt)


def datetime_file_string():
    dt = machine.RTC().datetime()
    return "{0:04d}-{1:02d}-{2:02d}T{4:02d}_{5:02d}_{6:02d}Z".format(*dt)


def date_string():
    dt = machine.RTC().datetime()
    return "{0:04d}-{1:02d}-{2:02d}".format(*dt)


def timestamp(dt):
    year = int(dt[0:4])
    month = int(dt[5:7])
    day = int(dt[8:10])
    hour = int(dt[11:13])
    minute = int(dt[14:16])
    second = int(dt[17:19])
    return time.mktime((year, month, day, hour, minute, second, 0, 0))


def uk_bst():
    # Return True if in UK BST - manually update bst_timestamps {} as needed
    dt = datetime_string()
    year = int(dt[0:4])
    ts = timestamp(dt)
    bst = False

    bst_timestamps = {
        2023: {"start": 1679792400, "end": 1698541200},
        2024: {"start": 1711846800, "end": 1729990800},
        2025: {"start": 1743296400, "end": 1761440400},
        2026: {"start": 1774746000, "end": 1792890000},
        2027: {"start": 1806195600, "end": 1824944400},
        2028: {"start": 1837645200, "end": 1856394000},
        2029: {"start": 1869094800, "end": 1887843600},
        2030: {"start": 1901149200, "end": 1919293200},
    }

    if year in bst_timestamps:
        if bst_timestamps[year]["start"] < ts and bst_timestamps[year]["end"] > ts:
            bst = True
    else:
        logging.warn(f"> Current year is not in BST lookup dictionary: {year}")
    return bst


def update_config(var_name, new_value):
    """Update a variable in config.py while keeping comments and order."""
    try:
        if isinstance(new_value, str):
            lower = new_value.strip().lower()
            if lower == "true":
                new_value = True
            elif lower == "false":
                new_value = False
            elif lower == "none":
                new_value = None
            else:
                # tenta converter para número, se possível
                try:
                    if "." in new_value:
                        new_value = float(new_value)
                    else:
                        new_value = int(new_value)
                except:
                    # mantém como string literal
                    pass

        # Update the value in memory
        setattr(config, var_name, new_value)

        # Format value for Python syntax
        if isinstance(new_value, str):
            new_value_str = f"'{new_value}'"
        elif new_value is None:
            new_value_str = "None"
        else:
            new_value_str = str(new_value)

        # Read original config file
        with open("config.py", "r") as f:
            lines = f.readlines()

        updated = False
        new_lines = []

        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith(var_name + " ="):
                # Keep inline comment (after '#') if present
                parts = line.split("#", 1)
                comment = ""
                if len(parts) > 1:
                    comment = "#" + parts[1].rstrip("\n")

                # Build updated line preserving comment
                new_line = f"{var_name} = {new_value_str}"
                if comment:
                    new_line += " " + comment
                new_line += "\n"

                new_lines.append(new_line)
                updated = True
            else:
                new_lines.append(line)

        # If variable not found, append it at the end
        if not updated:
            new_lines.append(f"\n{var_name} = {new_value_str}\n")

        # Write lines back to file (MicroPython-safe)
        with open("config.py", "w") as f:
            for line in new_lines:
                f.write(line)

        logging.info(f"Variable '{var_name}' updated to {new_value_str}")
        return True
    except Exception as e:
        logging.error(f"Error when updating variable '{var_name}'")
        return False


# Return the day number of your timestamp string accommodating UTC offsets
def timestamp_day(dt, offset_hours):
    # Bounce via timestamp to properly calculate hours change
    time = timestamp(dt)
    time = time + (offset_hours * 3600)
    dt = utime.localtime(time)
    day = int(dt[2])
    return day


def uid():
    return "{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}".format(
        *machine.unique_id()
    )


# file management helpers
# ===========================================================================
def file_size(filename):
    try:
        return os.stat(filename)[6]
    except OSError:
        return None


def file_exists(filename):
    try:
        return (os.stat(filename)[0] & 0x4000) == 0
    except OSError:
        return False


def mkdir_safe(path):
    try:
        os.mkdir(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        pass  # directory already exists, this is fine


def copy_file(source, target):
    with open(source, "rb") as infile:
        with open(target, "wb") as outfile:
            while True:
                chunk = infile.read(1024)
                if not chunk:
                    break
                outfile.write(chunk)


# temperature and humidity helpers
# ===========================================================================


# https://www.calctool.org/atmospheric-thermodynamics/absolute-humidity#what-is-and-how-to-calculate-absolute-humidity
def relative_to_absolute_humidity(relative_humidity, temperature_in_c):
    temperature_in_k = celcius_to_kelvin(temperature_in_c)
    actual_vapor_pressure = get_actual_vapor_pressure(
        relative_humidity, temperature_in_k
    )

    return actual_vapor_pressure / (
        WATER_VAPOR_SPECIFIC_GAS_CONSTANT * temperature_in_k
    )


def absolute_to_relative_humidity(absolute_humidity, temperature_in_c):
    temperature_in_k = celcius_to_kelvin(temperature_in_c)
    saturation_vapor_pressure = get_saturation_vapor_pressure(temperature_in_k)

    return (
        (WATER_VAPOR_SPECIFIC_GAS_CONSTANT * temperature_in_k * absolute_humidity)
        / saturation_vapor_pressure
        * 100
    )


def calculate_dewpoint(temperature_in_c, relative_humidity):
    alphatrh = (math.log((relative_humidity / 100))) + (
        (17.625 * temperature_in_c) / (243.04 + temperature_in_c)
    )
    dewpoint_in_c = (243.04 * alphatrh) / (17.625 - alphatrh)
    return dewpoint_in_c


def celcius_to_kelvin(temperature_in_c):
    return temperature_in_c + 273.15


def celcius_to_fahrenheit(temperature_in_c):
    return temperature_in_c * 1.8 + 32


def hpa_to_inches(pressure_in_hpa):
    return pressure_in_hpa * 0.02953


def metres_per_second_to_miles_per_hour(speed_in_mps):
    return speed_in_mps * 2.2369362912


def mm_to_inches(distance_in_mm):
    return distance_in_mm * 0.0393700787


def deg_to_vec(deg):
    rad = math.radians(deg % 360.0)
    return math.cos(rad), math.sin(rad)


def angular_diff(a, b):
    """Smallest signed diff a-b in degrees (-180..180)."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return d


def vec_to_deg(x, y):
    if x == 0 and y == 0:
        return 0.0
    ang = math.degrees(math.atan2(y, x))
    return (ang + 360.0) % 360.0


# https://www.calctool.org/atmospheric-thermodynamics/absolute-humidity#actual-vapor-pressure
# http://cires1.colorado.edu/~voemel/vp.html
def get_actual_vapor_pressure(relative_humidity, temperature_in_k):
    return get_saturation_vapor_pressure(temperature_in_k) * (relative_humidity / 100)


def get_saturation_vapor_pressure(temperature_in_k):
    v = 1 - (temperature_in_k / CRITICAL_WATER_TEMPERATURE)

    # empirical constants
    a1 = -7.85951783
    a2 = 1.84408259
    a3 = -11.7866497
    a4 = 22.6807411
    a5 = -15.9618719
    a6 = 1.80122502

    return CRITICAL_WATER_PRESSURE * math.exp(
        CRITICAL_WATER_TEMPERATURE
        / temperature_in_k
        * (a1 * v + a2 * v**1.5 + a3 * v**3 + a4 * v**3.5 + a5 * v**4 + a6 * v**7.5)
    )


# Calculates mean sea level pressure (QNH) from observed pressure
# https://keisan.casio.com/exec/system/1224575267
def get_sea_level_pressure(observed_pressure, temperature_in_c, altitude_in_m):
    # def sea(pressure, temperature, height):
    qnh = observed_pressure * (
        (
            1
            - (
                (0.0065 * altitude_in_m)
                / (temperature_in_c + (0.0065 * altitude_in_m) + 273.15)
            )
        )
        ** -5.257
    )
    return qnh


def get_battery_voltage():
    # Salva configuração do pino 29
    old_pad = machine.mem32[0x4001C000 | (4 + (4 * 29))]

    machine.mem32[0x4001C000 | (4 + (4 * 29))] = 128

    battery_voltage = 0
    for _ in range(VOLTAGE_SAMPLES):
        battery_voltage += _read_vsys_voltage()
        time.sleep_ms(20)

    battery_voltage = round(battery_voltage / VOLTAGE_SAMPLES, 3)

    # Restaura configuração do pino
    machine.mem32[0x4001C000 | (4 + (4 * 29))] = old_pad

    return battery_voltage


def _read_vsys_voltage():
    adc_Vsys = machine.ADC(ADC_CHANNEL)
    return adc_Vsys.read_u16() * 3.0 * ADC_VOLT_CONVERSION * VOLTAGE_CALIBRATION_FACTOR


def get_battery_percent(volts):
    """Interpolação da porcentagem com base na curva real."""
    if volts >= BATTERY_CURVE[0][0]:
        return 100
    if volts <= BATTERY_CURVE[-1][0]:
        return 0

    # Busca dois pontos da curva entre os quais está a tensão
    for i in range(len(BATTERY_CURVE) - 1):
        v_high, p_high = BATTERY_CURVE[i]
        v_low, p_low = BATTERY_CURVE[i + 1]
        if v_low <= volts <= v_high:
            # Interpolação linear entre os dois pontos
            ratio = (volts - v_low) / (v_high - v_low)
            return int(p_low + ratio * (p_high - p_low))
    return 0  # fallback (não deve ocorrer)
