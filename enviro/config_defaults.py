import config
from phew import logging

DEFAULT_USB_POWER_TEMPERATURE_OFFSET = 4.5
DEFAULT_SECONDARY_DESTINATION = None
DEFAULT_WIND_DIRECTION_OFFSET = 0
DEFAULT_UTC_OFFSET = 0
DEFAULT_UK_BST = True


def add_missing_config_settings():
    try:
        # check if ca file parameter is set, if not set it to not use SSL by setting to None
        config.mqtt_broker_ca_file
    except AttributeError:
        warn_missing_config_setting("mqtt_broker_ca_file")
        config.mqtt_broker_ca_file = None

    try:
        config.wind_direction_offset
    except AttributeError:
        warn_missing_config_setting("wind_direction_offset")
        config.wind_direction_offset = DEFAULT_WIND_DIRECTION_OFFSET

    try:
        config.wifi_country
    except AttributeError:
        warn_missing_config_setting("wifi_country")
        config.wifi_country = "GB"

    try:
        config.wunderground_id
    except AttributeError:
        warn_missing_config_setting("wunderground_id")
        config.wunderground_id = None

    try:
        config.wunderground_key
    except AttributeError:
        warn_missing_config_setting("wunderground_key")
        config.wunderground_key = None

    try:
        config.secondary_destination
    except AttributeError:
        warn_missing_config_setting("secondary_destination")
        config.secondary_destination = DEFAULT_SECONDARY_DESTINATION

    try:
        config.hass_discovery
    except AttributeError:
        warn_missing_config_setting("hass_discovery")
        config.hass_discovery = False

    try:
        config.hass_discovery_triggered
    except AttributeError:
        warn_missing_config_setting("hass_discovery_triggered")
        config.hass_discovery_triggered = False

    try:
        config.wind_direction_offset
    except AttributeError:
        warn_missing_config_setting("wind_direction_offset")
        config.wind_direction_offset = 0.0

    try:
        config.i2c_devices_cached
    except AttributeError:
        warn_missing_config_setting("i2c_devices_cached")
        config.i2c_devices_cached = [35, 81, 119]


def warn_missing_config_setting(setting):
    logging.warn(f"> config setting '{setting}' missing, please add it to config.py")
