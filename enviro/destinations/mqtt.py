from enviro import i2c_devices
from phew import logging
from enviro.constants import UPLOAD_SUCCESS, UPLOAD_FAILED, I2C_ADDR_LTR390, I2C_ADDR_INA219
from enviro.mqttsimple import MQTTClient
import ujson
import config


def log_destination():
    logging.debug(f"> uploading cached readings to MQTT broker: {config.mqtt_broker_address}")


def upload_reading(reading, mqtt_client=None):
    server = config.mqtt_broker_address
    username = config.mqtt_broker_username
    password = config.mqtt_broker_password
    nickname = reading["nickname"]

    try:
        local_client = False
        if mqtt_client is None:
            local_client = True
            if config.mqtt_broker_ca_file:
                # Using SSL
                f = open("ca.crt")
                ssl_data = f.read()
                f.close()
                mqtt_client = MQTTClient(
                    reading["uid"],
                    server,
                    user=username,
                    password=password,
                    keepalive=60,
                    ssl=True,
                    ssl_params={"cert": ssl_data},
                )
            else:
                # Not using SSL
                mqtt_client = MQTTClient(reading["uid"], server, user=username, password=password, keepalive=60)
            mqtt_client.connect()
        # Publish payload as UTF-8 bytes
        mqtt_client.publish(f"enviro/{nickname}", ujson.dumps(reading).encode("utf-8"), retain=True)
        if local_client:
            mqtt_client.disconnect()
        return UPLOAD_SUCCESS

    # Try disconnecting to see if it prevents hangs on this type of errors
    except (OSError, IndexError) as exc:
        try:
            import sys, io

            buf = io.StringIO()
            sys.print_exception(exc, buf)
            logging.debug(f"  - an exception occurred when uploading.", buf.getvalue())
            if local_client and mqtt_client is not None:
                mqtt_client.disconnect()
        except Exception as exc:
            import sys, io

            buf = io.StringIO()
            sys.print_exception(exc, buf)
            logging.debug(
                f"  - an exception occurred when disconnecting mqtt client.",
                buf.getvalue(),
            )

    except Exception as exc:
        import sys, io

        buf = io.StringIO()
        sys.print_exception(exc, buf)
        logging.debug(f"  - an exception occurred when uploading.", buf.getvalue())

    return UPLOAD_FAILED


def hass_discovery(board_type="weather"):
    logging.debug(f"> HASS Discovery initialized")
    try:
        server = config.mqtt_broker_address
        username = config.mqtt_broker_username
        password = config.mqtt_broker_password
        nickname = config.nickname
        mqtt_client = MQTTClient(nickname, server, user=username, password=password, keepalive=60)
        mqtt_client.connect()
        logging.debug(f"  - connected to mqtt broker")
    except:
        logging.error(f"! an exception try to connect to mqtt to send HASS Discovery")
        return

    # Core sensors common to weather
    mqtt_discovery(
        "Temperature",
        "temperature",
        "°C",
        "readings.temperature",
        board_type,
        mqtt_client,
        "mdi:thermometer",
    )
    mqtt_discovery(
        "Pressure",
        "pressure",
        "hPa",
        "readings.pressure",
        board_type,
        mqtt_client,
        "mdi:gauge",
    )
    mqtt_discovery(
        "Humidity",
        "humidity",
        "%",
        "readings.humidity",
        board_type,
        mqtt_client,
        "mdi:water-percent",
    )
    mqtt_discovery("Wifi Signal", "signal_strength", "dBm", "wifi", board_type, mqtt_client)

    # Weather-only sensors
    mqtt_discovery(
        "Luminance",
        "illuminance",
        "lx",
        "readings.luminance",
        board_type,
        mqtt_client,
        "mdi:brightness-5",
    )
    mqtt_discovery(
        "Wind Speed",
        "wind_speed",
        "m/s",
        "readings.wind_speed",
        board_type,
        mqtt_client,
        "mdi:weather-windy",
    )
    mqtt_discovery(
        "Wind Gust",
        "wind_speed",
        "m/s",
        "readings.wind_gust",
        board_type,
        mqtt_client,
        "mdi:weather-windy-variant",
    )
    mqtt_discovery(
        "Wind Direction",
        "none",
        "deg",
        "readings.wind_direction",
        board_type,
        mqtt_client,
        "mdi:compass",
    )
    mqtt_discovery(
        "Wind Direction Confidence",
        "none",
        "",
        "readings.wind_direction_confidence",
        board_type,
        mqtt_client,
        "mdi:target-variant",
    )
    mqtt_discovery(
        "Rain",
        "precipitation",
        "mm",
        "readings.rain",
        board_type,
        mqtt_client,
        "mdi:weather-rainy",
    )
    mqtt_discovery(
        "Rain Per Second",
        "precipitation",
        "mm/s",
        "readings.rain_per_second",
        board_type,
        mqtt_client,
        "mdi:weather-pouring",
    )
    mqtt_discovery(
        "Rain Per Hour",
        "precipitation",
        "mm/h",
        "readings.rain_per_hour",
        board_type,
        mqtt_client,
        "mdi:weather-pouring",
    )
    mqtt_discovery(
        "Rain Today",
        "precipitation",
        "mm",
        "readings.rain_today",
        board_type,
        mqtt_client,
        "mdi:weather-rainy",
    )
    mqtt_discovery(
        "Dew Point",
        "temperature",
        "°C",
        "readings.dewpoint",
        board_type,
        mqtt_client,
        "mdi:water",
    )
    mqtt_discovery(
        "Temperature Min",
        "temperature",
        "°C",
        "readings.temperature_min",
        board_type,
        mqtt_client,
        "mdi:thermometer-low",
    )
    mqtt_discovery(
        "Temperature Max",
        "temperature",
        "°C",
        "readings.temperature_max",
        board_type,
        mqtt_client,
        "mdi:thermometer-high",
    )
    mqtt_discovery(
        "Humidity Min",
        "humidity",
        "%",
        "readings.humidity_min",
        board_type,
        mqtt_client,
        "mdi:water-percent",
    )
    mqtt_discovery(
        "Humidity Max",
        "humidity",
        "%",
        "readings.humidity_max",
        board_type,
        mqtt_client,
        "mdi:water-percent",
    )
    mqtt_discovery(
        "Pollen Index",
        "aqi",
        "Index",
        "readings.pollen_index",
        board_type,
        mqtt_client,
        "mdi:flower-pollen",
    )

    # Optional UV sensor
    if I2C_ADDR_LTR390 in i2c_devices:
        logging.info(f"  - HASS Discovered sensor LTR390")
        mqtt_discovery(
            "UV",
            "uv_index",
            "UV Index",
            "readings.uv_index",
            board_type,
            mqtt_client,
            "mdi:weather-sunny-alert",
        )

    # Optional Voltage Sensor
    if I2C_ADDR_INA219 in i2c_devices:
        logging.info(f"  - HASS Discovered sensor INA219")
        mqtt_discovery(
            "Battery Voltage",
            "voltage",
            "V",
            "readings.battery_voltage",
            board_type,
            mqtt_client,
            "mdi:car-battery",
        )
        mqtt_discovery("Battery Percentage", "battery", "%", "readings.battery_percent", board_type, mqtt_client)

    logging.info(f"  - HASS Discovery package sent")
    mqtt_client.disconnect()
    logging.debug(f"  - disconnected from mqtt broker")


def mqtt_discovery(name, device_class, unit, value_name, model, mqtt_client, icon=None):
    nickname = config.nickname
    from ucollections import OrderedDict

    sensor_name = value_name.rsplit(".", 1)[-1]

    obj = OrderedDict(
        {
            "device": {
                "identifiers": [nickname],
                "name": nickname,
                "model": "Enviro " + model,
                "manufacturer": "Pimoroni",
            },
            "unit_of_measurement": unit,
            "device_class": device_class,
            "value_template": "{{ value_json." + value_name + " }}",
            "state_class": "measurement",
            "state_topic": "enviro/" + nickname,
            "name": name,
            "unique_id": "sensor." + nickname + "." + sensor_name,
        }
    )
    if icon:
        obj["icon"] = icon

    try:
        mqtt_client.publish(
            f"homeassistant/sensor/{nickname}/{sensor_name}/config",
            ujson.dumps(obj).encode("utf-8"),
            retain=True,
        )
        return UPLOAD_SUCCESS
    except:
        logging.error(
            f"! an exception occurred when sending HASS Discovery homeassistant/sensor/{nickname}/{sensor_name}/config"
        )
