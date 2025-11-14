import time
import math
import network
import rp2
import ubinascii
import enviro.helpers as helpers
from phew import logging
import config


class WifiManager:
    CYW43_LINK_DOWN = 0
    CYW43_LINK_JOIN = 1
    CYW43_LINK_NOIP = 2
    CYW43_LINK_UP = 3
    CYW43_LINK_FAIL = -1
    CYW43_LINK_NONET = -2
    CYW43_LINK_BADAUTH = -3

    

    def __init__(self, vbus_present, hostname_prefix="EnviroW-"):
        self.logging = logging
        self.helpers = helpers
        self.vbus_present = vbus_present
        self.hostname_prefix = hostname_prefix
        self._connected = False

        # Stores last known wifi signal strength (RSSI in dBm), or None
        self.last_signal_strength = None

    def reconnect(self, ssid, password, country, hostname=None):
        """Connect to wifi and return elapsed time in ms."""
        start_ms = time.ticks_ms()

        # Set country
        rp2.country(country)

        # Set hostname
        if hostname is None:
            hostname = "{}{}".format(self.hostname_prefix, self.helpers.uid()[-4:])
        network.hostname(hostname)

        status_names = {
            self.CYW43_LINK_DOWN: "Link is down",
            self.CYW43_LINK_JOIN: "Connected to wifi",
            self.CYW43_LINK_NOIP: "Connected to wifi, but no IP address",
            self.CYW43_LINK_UP: "Connected to wifi with an IP address",
            self.CYW43_LINK_FAIL: "Connection failed",
            self.CYW43_LINK_NONET: "No matching SSID found (could be out of range, or down)",
            self.CYW43_LINK_BADAUTH: "Authentication failure",
        }

        wlan = network.WLAN(network.STA_IF)

        def dump_status():
            status = wlan.status()
            self.logging.debug(
                "> active: {}, status: {} ({})".format(
                    1 if wlan.active() else 0,
                    status,
                    status_names.get(status, "unknown"),
                )
            )
            return status

        def wait_status(expected_status, timeout=10, tick_sleep=0.5):
            for _ in range(math.ceil(timeout / tick_sleep)):
                time.sleep(tick_sleep)
                status = dump_status()
                if status == expected_status:
                    return True
                if status < 0:
                    raise Exception(status_names.get(status, "error"))
            return False

        wlan.active(True)

        # Disable power saving mode if on USB power
        if self.vbus_present:
            wlan.config(pm=0xA11140)

        # Print MAC
        mac = ubinascii.hexlify(wlan.config("mac"), ":").decode()
        self.logging.debug("> MAC: " + mac)

        # Disconnect when necessary
        status = dump_status()
        if status >= self.CYW43_LINK_JOIN and status < self.CYW43_LINK_UP:
            self.logging.debug("> disconnecting...")
            wlan.disconnect()
            try:
                wait_status(self.CYW43_LINK_DOWN)
            except Exception as exc:
                raise Exception("Failed to disconnect: {}".format(exc))
        self.logging.debug("> ready for connection!")

        # Connect to AP
        self.logging.debug("> connecting to SSID {} (password: {})...".format(ssid, password))
        wlan.connect(ssid, password)
        try:
            wait_status(self.CYW43_LINK_UP)
        except Exception as exc:
            raise Exception("failed to connect to SSID {} (password: {}): {}".format(ssid, password, exc))

        self._connected = True
        self.logging.info("> wireless connected successfully!")

        # Try to read signal strength (RSSI)
        try:
            # On Pico W / ESP32 this is usually available as status('rssi')
            rssi = wlan.status("rssi")
            self.last_signal_strength = rssi
            self.logging.debug("> signal strength (RSSI): {} dBm".format(rssi))
        except Exception:
            # If not supported, keep None
            self.last_signal_strength = None
            self.logging.debug("> dignal strength (RSSI) not available on this firmware")

        ip, subnet, gateway, dns = wlan.ifconfig()
        self.logging.info("> IP: {}, Subnet: {}, Gateway: {}, DNS: {}".format(ip, subnet, gateway, dns))

        elapsed_ms = time.ticks_ms() - start_ms
        self.logging.debug("> Elapsed: {}ms".format(elapsed_ms))
        return elapsed_ms

    def connect(self):
        """Connect using wifi_* fields from config."""
        if (self._connected == True):
            self.logging.debug("> wireless already connected - Skipping")
            return True
        try:
            self.logging.debug("> connecting to wifi network '{}'".format(config.wifi_ssid))
            elapsed_ms = self.reconnect(config.wifi_ssid, config.wifi_password, config.wifi_country)
            seconds_to_connect = elapsed_ms / 1000
            if seconds_to_connect > 5:
                self.logging.warn("  - took {} seconds to connect to wifi".format(seconds_to_connect))
            return True
        except Exception as exc:
            self.logging.error("! {}".format(exc))
            return False

    def disconnect(self):
        """Disconnect wifi and turn interface off."""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.disconnect()
        wlan.active(False)
        self.last_signal_strength = None
        self._connected = False
        self.logging.info("> disconnecting wireless after operation")

    def get_last_signal_strength(self):
        """
        Return last known wifi signal strength (RSSI in dBm),
        or None if connection has never succeeded or RSSI is unavailable.
        """
        return self.last_signal_strength
