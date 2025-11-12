import time, math
from breakout_bme280 import BreakoutBME280  # type: ignore
from breakout_ltr559 import BreakoutLTR559  # type: ignore
from ucollections import OrderedDict
from machine import Pin
from pimoroni import Analog  # type: ignore
import ujson
from enviro import i2c, leds_manager, config, constants
import enviro.helpers as helpers
from phew import logging

# ================================================================
# 🔧 Constants & Variables
# ================================================================
# amount of rain required for the bucket to tip in mm
RAIN_MM_PER_TICK = 0.2794

# distance from the centre of the anemometer to the centre
# of one of the cups in cm
WIND_CM_RADIUS = 7.0
# scaling factor for wind speed in m/s
WIND_FACTOR = 0.0218
DAILY_STATS_FILE = "daily_stats.json"

_daily_stats_cache = None
_daily_dirty = False
_last_rain_flush_ms = 0
bme280 = BreakoutBME280(i2c, constants.I2C_ADDR_BME280)
ltr559 = BreakoutLTR559(i2c)

wind_direction_pin = Analog(constants.WIND_DIRECTION_PIN)
wind_speed_pin = Pin(constants.WIND_SPEED_PIN, Pin.IN, Pin.PULL_UP)
rain_pin = Pin(constants.RAIN_PIN, Pin.IN, Pin.PULL_DOWN)
last_rain_trigger = False

# ================================================================
# 📊 Unified Daily Statistics System
# ================================================================


def load_daily_stats():
    global _daily_stats_cache
    if _daily_stats_cache is not None and _daily_stats_cache.get("date") == helpers.date_string():
        return _daily_stats_cache

    """Load or create daily statistics JSON file."""
    today = helpers.date_string()
    base = {
        "date": today,
        "rain_ticks": 0,
        "rain_total_mm": 0.0,
        "rain_events": [],  # NEW: timestamps (ISO strings) for per-hour calc
        "rain_last_count": 0,  # NEW: tick counter at last reading (to get delta)
        "wind_gust": 0.0,
        "wind_samples": [],
        "temperature": {"min": 999.0, "max": -999.0, "sum": 0.0, "count": 0},
        "humidity": {"min": 999.0, "max": -999.0, "sum": 0.0, "count": 0},
    }

    if helpers.file_exists(DAILY_STATS_FILE):
        try:
            with open(DAILY_STATS_FILE, "r") as f:
                data = ujson.load(f)
            if data.get("date") == today:
                base.update(data)
            else:
                logging.info("> New day detected — resetting daily stats.")
                save_daily_stats(base)
        except Exception as e:
            logging.error(f"! Failed to read {DAILY_STATS_FILE}: {e}")
            save_daily_stats(base)
    else:
        save_daily_stats(base)

    _daily_stats_cache = base
    return base


def save_daily_stats(data):
    global _daily_stats_cache
    """Save stats to JSON file."""
    _daily_stats_cache = data
    with open(DAILY_STATS_FILE, "w") as f:
        ujson.dump(data, f)


def load_dir_state():
    data = load_daily_stats()
    s = data.get("wind_dir_state", None)
    if not s:
        s = {"ema_x": 0.0, "ema_y": 0.0}
        data["wind_dir_state"] = s
        mark_dirty()
    return s


def save_dir_state(ema_x, ema_y):
    data = load_daily_stats()
    data["wind_dir_state"] = {"ema_x": ema_x, "ema_y": ema_y}
    mark_dirty()


def mark_dirty():
    global _daily_dirty
    _daily_dirty = True


def save_daily_stats_if_needed(force=False):
    global _daily_dirty, _daily_stats_cache
    if _daily_stats_cache is None:
        return
    if not _daily_dirty and not force:
        return
    with open(DAILY_STATS_FILE, "w") as f:
        ujson.dump(_daily_stats_cache, f)
    _daily_dirty = False


def startup(reason):
    logging.info(f"> starting weather")
    global last_rain_trigger

    try:
        import wakeup  # type: ignore

        rain_sensor_trigger = wakeup.get_gpio_state() & (1 << 10)
    except Exception:
        rain_sensor_trigger = 0

    if rain_sensor_trigger:
        # read the current rain entries
        log_rain()

        last_rain_trigger = True

        # if we were woken by the RTC or a Poke continue with the startup
        return (reason == constants.WAKE_REASON_RTC_ALARM) or (reason == constants.WAKE_REASON_BUTTON_PRESS)

    # there was no rain trigger so continue with the startup
    return True


def check_trigger():
    global last_rain_trigger
    rain_sensor_trigger = rain_pin.value()

    if rain_sensor_trigger and not last_rain_trigger:
        leds_manager.set_activity_led(100)
        time.sleep(0.05)
        leds_manager.set_activity_led(0)

        logging.info(f"> add new rain trigger at {helpers.datetime_string()}")
        log_rain()

    last_rain_trigger = rain_sensor_trigger


# ================================================================
# ☔ Rain Handling
# ================================================================


def log_rain():
    global _last_rain_flush_ms
    """Add one rain bucket tip, store timestamp, and update totals."""
    data = load_daily_stats()

    data["rain_ticks"] += 1
    data["rain_total_mm"] = data["rain_ticks"] * RAIN_MM_PER_TICK

    # append timestamp for per-hour computation
    ts = helpers.datetime_string()
    events = data.get("rain_events", [])
    events.append(ts)
    # keep at most ~190 events (fits < one FS block comfortably)
    if len(events) > 190:
        events = events[-190:]
    data["rain_events"] = events
    mark_dirty()

    now = time.ticks_ms()
    if time.ticks_diff(now, _last_rain_flush_ms) > 5000:
        save_daily_stats_if_needed(force=True)
        _last_rain_flush_ms = now

    logging.info(f"> Rain tick recorded ({data['rain_total_mm']} mm total)")


# ================================================================
# 💨 Wind Handling
# ================================================================


def wind_speed(sample_time_ms=1000):
    """Measure current wind speed in m/s."""
    state = wind_speed_pin.value()
    first = last = None
    transitions = 0
    start = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), start) <= sample_time_ms:
        new_state = wind_speed_pin.value()
        if new_state != state:
            tick_time = time.ticks_ms()
            if first is None:
                first = tick_time
            last = tick_time
            transitions += 1
            state = new_state

    if transitions < 2 or first == last:
        return 0.0

    avg_tick_ms = time.ticks_diff(last, first) / (transitions - 1)
    if avg_tick_ms == 0:
        return 0.0

    rotation_hz = (1000.0 / avg_tick_ms) / 2.0
    circumference = WIND_CM_RADIUS * 2.0 * math.pi
    return rotation_hz * circumference * WIND_FACTOR


def update_wind_stats(current_speed):
    """Update average and max gust in daily stats."""
    data = load_daily_stats()
    data["wind_samples"].append(current_speed)
    if len(data["wind_samples"]) > 50:
        data["wind_samples"] = data["wind_samples"][-50:]
    if current_speed > data.get("wind_gust", 0):
        data["wind_gust"] = round(current_speed, 2)
    mark_dirty()
    avg_speed = sum(data["wind_samples"]) / len(data["wind_samples"])
    return round(avg_speed, 2), data["wind_gust"]


# ================================================================
# 🌬️ Wind Direction
# ================================================================


def smooth_direction(dir_deg, speed_mps, alpha_base=0.25, min_speed=0.8, hysteresis_deg=8.0):
    """
    Speed-weighted exponential moving average for wind direction.
    - Ignores updates when speed is below min_speed (too turbulent).
    - Applies hysteresis: if change is small and speed is low, skip.
    - Persists EMA state in daily_stats.json.
    Returns (smoothed_dir_deg, confidence_0_1).
    """
    state = load_dir_state()
    ema_x = state.get("ema_x", 0.0)
    ema_y = state.get("ema_y", 0.0)

    # If too calm, do not update; just return current estimate
    if speed_mps < min_speed and (ema_x != 0.0 or ema_y != 0.0):
        R = math.sqrt(ema_x * ema_x + ema_y * ema_y)
        return helpers.vec_to_deg(ema_x, ema_y), max(0.0, min(1.0, R))

    # Compute current EMA direction for hysteresis decision
    current_dir = helpers.vec_to_deg(ema_x, ema_y) if (ema_x != 0.0 or ema_y != 0.0) else dir_deg
    if abs(helpers.angular_diff(dir_deg, current_dir)) < hysteresis_deg and speed_mps < (min_speed * 1.5):
        # change too small under low speed → skip update
        R = math.sqrt(ema_x * ema_x + ema_y * ema_y)
        return current_dir, max(0.0, min(1.0, R))

    # Speed-weight alpha: stronger wind → faster response
    # Clamp weight between 0.5x..2x the base alpha
    speed_weight = max(0.5, min(2.0, speed_mps / 3.0))
    alpha = max(0.05, min(0.8, alpha_base * speed_weight))

    vx, vy = helpers.deg_to_vec(dir_deg)
    ema_x = (1.0 - alpha) * ema_x + alpha * vx
    ema_y = (1.0 - alpha) * ema_y + alpha * vy

    # Persist
    save_dir_state(ema_x, ema_y)

    # Output
    R = math.sqrt(ema_x * ema_x + ema_y * ema_y)  # confidence proxy
    smoothed = helpers.vec_to_deg(ema_x, ema_y)
    return smoothed, max(0.0, min(1.0, R))


def wind_direction():
    ADC_TO_DEGREES = (
        2.533,
        1.308,
        1.487,
        0.270,
        0.300,
        0.212,
        0.595,
        0.408,
        0.926,
        0.789,
        2.031,
        1.932,
        3.046,
        2.667,
        2.859,
        2.265,
    )

    value = wind_direction_pin.read_voltage()
    closest_index = min(range(16), key=lambda i: abs(ADC_TO_DEGREES[i] - value))
    wind_dir = closest_index * 22.5
    offset = getattr(config, "wind_direction_offset", 0.0)
    return (wind_dir + 360.0 + offset) % 360.0


# ================================================================
# 🌧️ Rain Summary
# ================================================================


def rainfall(seconds_since_last):
    """
    Returns:
      amount (mm since last reading),
      per_second (mm/s over last interval),
      per_hour (mm in last 3600s),
      today (mm total today)
    """
    data = load_daily_stats()

    ticks_now = data.get("rain_ticks", 0)
    last_count = data.get("rain_last_count", ticks_now)

    # amount since last reading (in mm)
    delta_ticks = max(0, ticks_now - last_count)
    amount = round(delta_ticks * RAIN_MM_PER_TICK, 4)

    # mm/s since last reading
    per_second = 0.0
    if seconds_since_last and seconds_since_last > 0:
        per_second = round(amount / float(seconds_since_last), 6)

    # mm in last 3600s window, using timestamped events
    per_hour = 0.0
    events = data.get("rain_events", [])
    if events:
        now_ts = helpers.timestamp(helpers.datetime_string())
        one_hour_ago = now_ts - 3600
        tips_last_hour = 0
        for iso in events:
            try:
                t = helpers.timestamp(iso)
                if t >= one_hour_ago:
                    tips_last_hour += 1
            except Exception:
                pass
        per_hour = round(tips_last_hour * RAIN_MM_PER_TICK, 4)

    # total today in mm
    today = round(data.get("rain_total_mm", 0.0), 3)

    # update last_count so next read reports only the new delta
    data["rain_last_count"] = ticks_now
    mark_dirty()

    return amount, per_second, per_hour, today


# ================================================================
# 🌻 Pollen Index
# ================================================================


def estimate_pollen_index(temperature, humidity, wind_speed, rain_today, luminance):
    """
    Retorna um índice de 0 a 5 baseado em condições ambientais.
    Essa estimativa é qualitativa — não mede pólen diretamente.
    """
    score = 0

    # Temperatura: mais calor, mais liberação de pólen
    if temperature > 15:
        score += 1
    if temperature > 20:
        score += 1
    if temperature > 25:
        score += 1

    # Umidade: baixa umidade → pólen se dispersa mais
    if humidity < 70:
        score += 1
    if humidity < 50:
        score += 1

    # Vento: mais vento → transporte de pólen
    if wind_speed > 2:
        score += 1
    if wind_speed > 4:
        score += 1

    # Chuva: reduz concentração temporariamente
    if rain_today > 0:
        score -= 2

    # Luminosidade: dias ensolarados favorecem liberação
    if luminance > 10000:
        score += 1

    # Mantém dentro dos limites 0–5
    score = max(0, min(5, score))
    return int(score)


# ================================================================
# 🌡️ Temperature and Humidity Tracking
# ================================================================


def update_temp_humidity_stats(temp, hum):
    """Update daily min, max, and average for temperature and humidity."""
    data = load_daily_stats()

    for key, value in [("temperature", temp), ("humidity", hum)]:
        stats = data[key]
        stats["min"] = min(stats["min"], value)
        stats["max"] = max(stats["max"], value)
        stats["sum"] += value
        stats["count"] += 1
        data[key] = stats

    mark_dirty()
    return round(data["temperature"]["sum"] / data["temperature"]["count"], 2), round(
        data["humidity"]["sum"] / data["humidity"]["count"], 2
    )


# ================================================================
# 📈 Main Sensor Readings
# ================================================================


def get_sensor_readings(seconds_since_last, is_usb_power):
    bme280.read()
    time.sleep(0.1)
    bme280_data = bme280.read()
    ltr_data = ltr559.get_reading()
    rain, rain_per_second, rain_per_hour, rain_today = rainfall(seconds_since_last)

    pressure = bme280_data[1] / 100.0
    temperature = bme280_data[0]
    humidity = bme280_data[2]

    avg_temp, avg_hum = update_temp_humidity_stats(temperature, humidity)

    current_wind = wind_speed()
    avg_wind, gust_wind = update_wind_stats(current_wind)
    raw_wind_dir = wind_direction()
    smoothed_dir, dir_conf = smooth_direction(raw_wind_dir, avg_wind)
    daily_stats = load_daily_stats()

    readings = OrderedDict(
        {
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "pressure": round(pressure, 2),
            "luminance": round(ltr_data[BreakoutLTR559.LUX], 2),
            "wind_speed": avg_wind,
            "wind_gust": gust_wind,
            "wind_direction": smoothed_dir,
            "wind_direction_confidence": round(dir_conf, 3),
            # ✅ Rain metrics restored
            "rain": round(rain, 4),
            "rain_per_second": round(rain_per_second, 6),
            "rain_per_hour": round(rain_per_hour, 4),
            "rain_today": round(rain_today, 3),
            "dewpoint": round(helpers.calculate_dewpoint(temperature, humidity), 2),
            "temperature_avg": avg_temp,
            "temperature_min": round(daily_stats["temperature"]["min"], 2),
            "temperature_max": round(daily_stats["temperature"]["max"], 2),
            "humidity_avg": avg_hum,
            "humidity_min": round(daily_stats["humidity"]["min"], 2),
            "humidity_max": round(daily_stats["humidity"]["max"], 2),
            "pollen_index": estimate_pollen_index(
                temperature,
                humidity,
                avg_wind,
                rain_today,
                ltr_data[BreakoutLTR559.LUX],
            ),
        }
    )

    save_daily_stats_if_needed()
    return readings
