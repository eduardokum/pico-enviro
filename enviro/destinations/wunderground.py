from enviro import logging
from enviro.constants import UPLOAD_SUCCESS, UPLOAD_FAILED
import urequests
import config
from enviro.helpers import (
    celcius_to_fahrenheit,
    hpa_to_inches,
    metres_per_second_to_miles_per_hour,
    mm_to_inches,
    hpa_to_inches,
)


def log_destination():
    logging.info(
        f"> uploading cached readings to Weather Underground device: {config.wunderground_id}"
    )


def get_wunderground_timestamp(enviro_timestamp):
    year = enviro_timestamp[0:4]
    month = enviro_timestamp[5:7]
    day = enviro_timestamp[8:10]
    hour = enviro_timestamp[11:13]
    minute = enviro_timestamp[14:16]
    second = enviro_timestamp[17:19]
    timestamp = (
        year + "-" + month + "-" + day + "+" + hour + "%3A" + minute + "%3A" + second
    )
    return timestamp


# API documentation https://support.weather.com/s/article/PWS-Upload-Protocol?language=en_GB
def upload_reading(reading):
    timestamp = get_wunderground_timestamp(reading["timestamp"])

    url = (
        "https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php?"
        f"ID={config.wunderground_id}&PASSWORD={config.wunderground_key}"
        f"&dateutc={timestamp}&softwaretype=EnviroWeather&action=updateraw"
    )
    readings = reading["readings"]

    # Temperature (°C → °F)
    if "temperature" in readings:
        url += "&tempf=" + str(celcius_to_fahrenheit(readings["temperature"]))

    # Temperature Max / Min / Avg (°C → °F)
    if "temperature_max" in readings:
        url += "&tempfmax=" + str(celcius_to_fahrenheit(readings["temperature_max"]))
    if "temperature_min" in readings:
        url += "&tempfmin=" + str(celcius_to_fahrenheit(readings["temperature_min"]))
    if "temperature_avg" in readings:
        url += "&tempavgf=" + str(celcius_to_fahrenheit(readings["temperature_avg"]))

    # Humidity (%)
    if "humidity" in readings:
        humidity = min(readings["humidity"], 100)
        url += "&humidity=" + str(humidity)

    # Dew point (°C → °F)
    if "dewpoint" in readings:
        url += "&dewptf=" + str(celcius_to_fahrenheit(readings["dewpoint"]))

    # Pressure (hPa → inHg)
    if "sea_level_pressure" in readings:
        url += "&baromin=" + str(hpa_to_inches(readings["sea_level_pressure"]))
    elif "pressure" in readings:
        url += "&baromin=" + str(hpa_to_inches(readings["pressure"]))

    # Wind speed (m/s → mph)
    if "wind_speed" in readings:
        url += "&windspeedmph=" + str(
            metres_per_second_to_miles_per_hour(readings["wind_speed"])
        )

    # Wind gust (m/s → mph)
    if "wind_gust" in readings:
        url += "&windgustmph=" + str(
            metres_per_second_to_miles_per_hour(readings["wind_gust"])
        )

    # Wind direction (°)
    if "wind_direction" in readings:
        url += "&winddir=" + str(readings["wind_direction"])

    # Rain last hour (mm → inches)
    if "rain_per_hour" in readings:
        url += "&rainin=" + str(mm_to_inches(readings["rain_per_hour"]))

    # Rain today (mm → inches)
    if "rain_today" in readings:
        url += "&dailyrainin=" + str(mm_to_inches(readings["rain_today"]))

    # Solar radiation (lux → W/m² approximation)
    if "luminance" in readings:
        solarrad = round(readings["luminance"] / 120.0, 2)
        url += "&solarradiation=" + str(solarrad)

    # UV index (if LTR390 present)
    if "uv_index" in readings:
        url += "&UV=" + str(readings["uv_index"])

    try:
        # send (GET) reading data to http endpoint
        result = urequests.get(url)

        result.close()

        if result.status_code == 200:
            return UPLOAD_SUCCESS

        logging.debug(f"  - upload issue ({result.status_code} {result.reason})")
    except:
        logging.debug(f"  - an exception occurred when uploading")

    return UPLOAD_FAILED
