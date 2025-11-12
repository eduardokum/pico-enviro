# Wi-Fi settings
WIFI_SSID = "UAI-FAI-AIOTI"
WIFI_PASSWORD = "393act2978"

# MQTT settings
MQTT_BROKER = "10.18.100.123"
MQTT_PORT = 1883
MQTT_TOPIC = "enviro/weather"
# If your broker requires auth, fill these:
MQTT_USERNAME = "eduardo"
MQTT_PASSWORD = "10228@E26c27#2601199"


# Timing (seconds / milliseconds)
READ_INTERVAL_SECONDS = 300  # 5 minutes between readings
WIFI_TIMEOUT_MS = 15000  # 15 seconds to connect Wi-Fi
WDT_TIMEOUT_MS = 20000  # 20 seconds watchdog timeout
