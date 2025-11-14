# lib/ota_light.py
import os, ujson, uhashlib, machine, time, network
from phew import logging
import enviro
from enviro.version import __version__
import urequests

MANIFEST_URL = (
    "https://raw.githubusercontent.com/eduardokum/enviro/main/releases/manifest.json"
)
LAST_CHECK_FILE = "ota.txt"
CHECK_INTERVAL_HOURS = 24  # check for OTA updates every 24 hours


def _wifi_connected():
    if not enviro.wifi_manager.connect():
        return False
    return True


def _https_get(url):
    """Perform an HTTPS GET using urequests (built-in SSL)."""
    if not _wifi_connected():
        logging.error("! OTA - Wi-Fi is not connected — cannot fetch {}".format(url))
        return None

    try:
        r = urequests.get(url)
        status = getattr(r, "status_code", 200)
        if status != 200:
            logging.error("! OTA HTTP {} while fetching {}".format(status, url))
            r.close()
            return None
        
        data = r.content
        r.close()
        return data
    except Exception as e:
        logging.error("! OTA Failed to fetch {}: {}".format(url, e))
        return None


def _sha256(b):
    """Return SHA-256 hash of bytes."""
    h = uhashlib.sha256()
    h.update(b)
    return "".join("{:02x}".format(x) for x in h.digest())


def _safe_write(path, data):
    """Safely write data to file, creating directories as needed."""
    dirs = path.split("/")[:-1]
    p = ""
    for d in dirs:
        if not d:
            continue
        p += "/" + d
        try:
            os.mkdir(p)
        except OSError:
            pass
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(tmp, path)


def _read_file(path):
    """Read file contents, returning None if not found."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except:
        return None


def check_and_update():
    try:
        """Check if should try the OTA"""
        last_ts = _read_last_check()
        now = _rtc_timestamp()
        hours = (now - last_ts) / 3600.0 if last_ts else CHECK_INTERVAL_HOURS + 1
        if hours < CHECK_INTERVAL_HOURS:
            logging.debug("> OTA - Skipped — last check was too recent.")
            return False

        if not _wifi_connected():
            logging.error("! OTA Cannot check for update — Wi-Fi not connected.")
            return False

        logging.debug("> OTA initializing")
        logging.debug("  - OTA Checking firmware version...")

        mraw = _https_get(MANIFEST_URL)
        if not mraw:
            logging.error("! OTA Failed to download manifest file.")
            return False

        try:
            manifest = ujson.loads(mraw)
        except Exception as e:
            logging.error("! OTA Invalid manifest JSON: {}".format(e))
            return False

        new_version = manifest.get("version")

        if new_version == __version__:
            _write_last_check(now)
            logging.debug("  - OTA Firmware already up to date.")
            return False

        logging.info("  - OTA New firmware version available: {}".format(new_version))
        for f in manifest["files"]:
            path = f["path"]
            url = f["url"]
            expected = f["sha256"]

            local = _read_file(path)
            if local and _sha256(local) == expected:
                # Local file already matches expected hash
                continue

            logging.debug("  - OTA Updating file: {}".format(path))
            data = _https_get(url)

            if data is None:
                logging.error("! OTA Failed to download file: {}".format(path))
                continue

            checksum = _sha256(data)
            if checksum != expected:
                logging.warn("  - OTA Invalid hash for file: {}, skipping.".format(path))
                continue

            _safe_write(path, data)
            logging.debug("  - OTA File updated successfully: {}".format(path))

        logging.info("  - OTA Firmware update applied successfully")
        _safe_write("enviro/version.py", f'__version__ = "{new_version}"\n')
        _write_last_check(now)

        try:
            with open("config.py", "r") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                stripped = line.lstrip()
                if stripped.startswith("hass_discovery_triggered ="):
                    # Build updated line preserving comment
                    new_line = f"hass_discovery_triggered = False\n"
                    new_lines.append(new_line)
                else:
                    new_lines.append(line)

            # Write lines back to file (MicroPython-safe)
            with open("config.py", "w") as f:
                for line in new_lines:
                    f.write(line)

            logging.debug("  - OTA hass_discovery_triggered updated to False")
        except:
            pass

        logging.debug("  - OTA rebooting...")

        time.sleep(2)
        machine.reset()
        return True
    except Exception as e:
        logging.error("! OTA - failed:", e)


def _ensure_dir(path):
    """Create directories recursively (MicroPython compatible)."""
    parts = path.split("/")
    current = ""
    for p in parts:
        if not p:
            continue
        current += "/" + p
        try:
            os.mkdir(current)
        except OSError:
            pass  # already exists


def _read_last_check():
    """Read timestamp of last OTA check."""
    try:
        with open(LAST_CHECK_FILE, "r") as f:
            return float(f.read().strip())
    except:
        return 0.0


def _write_last_check(ts):
    """Write timestamp of last OTA check."""
    with open(LAST_CHECK_FILE, "w") as f:
        f.write(str(ts))


def _rtc_timestamp():
    """Return timestamp from RTC (seconds since epoch)."""
    try:
        y, m, d, wd, hh, mm, ss, _ = machine.RTC().datetime()
        import utime

        return utime.mktime((y, m, d, hh, mm, ss, 0, 0))
    except:
        return time.time()
