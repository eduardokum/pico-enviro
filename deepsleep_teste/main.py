import time
import json
import ubinascii

import network
import machine
import sys
from machine import I2C, Pin
from pimoroni_i2c import PimoroniI2C
from breakout_bme280 import BreakoutBME280
from breakout_ltr559 import BreakoutLTR559
import config

# LED setup (on-board LED on Pico W)
led = Pin("LED", Pin.OUT)


def blink_led(times=1, delay_ms=150):
    """Blink on-board LED a few times."""
    for _ in range(times):
        led.on()
        time.sleep_ms(delay_ms)
        led.off()
        time.sleep_ms(delay_ms)


blink_led(1)

# Create watchdog as early as possible (RP2040 max ~8388 ms)
# WDT_MAX_TIMEOUT_MS = 8000
# wdt = WDT(timeout=min(config.WDT_TIMEOUT_MS, WDT_MAX_TIMEOUT_MS))


def connect_wifi():
    """Connect to Wi-Fi and return wlan object."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        start = time.ticks_ms()

        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > config.WIFI_TIMEOUT_MS:
                raise RuntimeError("WiFi connection timeout")
            time.sleep_ms(200)

    return wlan


def read_sensors():
    """Read BME280 and LTR559 sensors and return dict with values."""

    print("Stage: creating I2C")
    i2c = PimoroniI2C(4, 5, 100000)

    try:
        print("Stage: creating BME280")
        bme280 = BreakoutBME280(i2c, 0x77)

        print("Stage: creating LTR559")
        ltr559 = BreakoutLTR559(i2c)

        print("Stage: reading BME280")
        bme280.read()
        time.sleep(0.1)
        bme280_data = bme280.read()

        print("Stage: reading LTR559")
        ltr_data = ltr559.get_reading()

        pressure = bme280_data[1] / 100.0
        temperature = bme280_data[0]
        humidity = bme280_data[2]

        reading = {
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "pressure": round(pressure, 2),
            "luminance": round(ltr_data[BreakoutLTR559.LUX], 2),
        }

        print("Stage: sensors ok:", reading)
        return reading

    except OSError as exc:
        # Erro típico de I2C (Errno 1, etc.)
        print("I2C / sensor OS error:", exc)
        # Relevante para debug: propaga pro handler de cima
        raise


def publish_to_mqtt(payload_dict):
    """Publish JSON payload to MQTT broker."""
    from umqtt.simple import MQTTClient, MQTTException

    client = MQTTClient(
        client_id=b"test-client",
        server=config.MQTT_BROKER,
        port=config.MQTT_PORT,
        user=config.MQTT_USERNAME,
        password=config.MQTT_PASSWORD,
    )

    try:
        client.connect()
        payload = json.dumps(payload_dict)
        client.publish(config.MQTT_TOPIC, payload)
        client.disconnect()

        # Indicate success with LED blink
        print("MQTT publish ok")
        blink_led(times=2, delay_ms=120)

    except MQTTException as exc:
        # Error returned by MQTT broker (like code 5 = not authorized)
        print("MQTT error:", exc)
        blink_led(times=3, delay_ms=80)

    except OSError as exc:
        # Network / socket error
        print("MQTT OS error:", exc)
        blink_led(times=4, delay_ms=80)

    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def main_loop():
    """One full cycle: Wi-Fi -> read sensors -> MQTT -> sleep."""

    # Connect Wi-Fi
    wlan = connect_wifi()

    # Read sensors
    readings = read_sensors()

    # Add timestamp from RTC (if configured) or simple uptime
    readings["uptime_ms"] = time.ticks_ms()

    # Publish
    publish_to_mqtt(readings)

    # Turn off Wi-Fi to save power
    try:
        wlan.active(False)
    except Exception:
        pass

    # Small delay before sleep
    time.sleep(1)

    # Sleep for configured interval (seconds)
    print("Sleeping for", config.READ_INTERVAL_SECONDS, "seconds")
    time.sleep(config.READ_INTERVAL_SECONDS)


# Entry point
while True:
    try:
        main_loop()
    except Exception as exc:
        # Print as much debug info as possible
        try:
            print("Fatal error type:", type(exc))
            print("Fatal error repr:", repr(exc))
            sys.print_exception(exc)
        except Exception:
            pass

        # pisca pra avisar erro e tenta de novo depois
        blink_led(times=5, delay_ms=80)
        time.sleep(5)
