# enviro config file

# you may edit this file by hand but if you enter provisioning mode
# then the file will be automatically overwritten with new details

provisioned = False

# enter a nickname for this board
nickname = None

# network access details
wifi_ssid = None
wifi_password = None
wifi_country = "GB"

# how often to wake up and take a reading (in minutes)
reading_frequency = 15

# how often to trigger a resync of the onboard RTC (in hours)
resync_frequency = 168

# upload destination (simplified to MQTT only)
destination = "mqtt"
# secondary upload destination
secondary_destination = None

# how often to upload data (number of cached readings)
upload_frequency = 5

# Watchdog timer in whole minutes (integer), 0 is not active
pio_watchdog_time = 10

# mqtt broker settings
mqtt_broker_address = None
mqtt_broker_username = None
mqtt_broker_password = None
# mqtt broker if using local SSL
mqtt_broker_ca_file = None

# Home Assistant Discovery setting
hass_discovery = False
hass_discovery_triggered = False

# weather specific settings
wind_direction_offset = 0

# Feature toggles
enable_battery_voltage = False

# voltage calibration
voltage_calibration_factor = 1.000
