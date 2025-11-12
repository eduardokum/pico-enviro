from enviro.constants import *
from machine import Pin

hold_vsys_en_pin = Pin(HOLD_VSYS_EN_PIN, Pin.OUT, value=True)

from pimoroni_i2c import PimoroniI2C
from led_manager import LedManager
import time
import config
from phew import logging

i2c = PimoroniI2C(I2C_SDA_PIN, I2C_SCL_PIN, 100000)
i2c_devices = i2c.scan()

model = "weather"


# return the module that implements this board type
def get_board():
    import enviro.boards.weather as board

    return board


# set up the activity led
# ===========================================================================
leds_manager = LedManager()

# check whether device needs provisioning
# ===========================================================================

button_pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_DOWN)
needs_provisioning = False
start = time.time()
while button_pin.value():  # button held for 3 seconds go into provisioning
    if time.time() - start > 3:
        needs_provisioning = True
        break

try:
    if not config.provisioned:  # provisioned flag not set go into provisioning
        needs_provisioning = True
except Exception as e:
    logging.error("> missing or corrupt config.py", e)
    needs_provisioning = True

if needs_provisioning:
    logging.info("> entering provisioning mode")
    import enviro.provisioning


# Start reading here
# ===========================================================================
import machine, sys, os, ujson
from machine import RTC, ADC
import phew
import math
from pcf85063a import PCF85063A
import enviro.config_defaults as config_defaults
import enviro.helpers as helpers
from wifi_manager import WifiManager

# read the state of vbus to know if we were woken up by USB
vbus_present = Pin("WL_GPIO2", Pin.IN).value()

# create wifi object
wifi_manager = WifiManager(vbus_present)

config_defaults.add_missing_config_settings()

# set up the button, external trigger, and rtc alarm pins
rtc_alarm_pin = Pin(RTC_ALARM_PIN, Pin.IN, Pin.PULL_DOWN)

# intialise the pcf85063a real time clock chip
rtc = PCF85063A(i2c)
i2c.writeto_mem(0x51, 0x00, b"\x00")  # ensure rtc is running (this should be default?)
rtc.enable_timer_interrupt(False)

t = rtc.datetime()
# BUG ERRNO 22, EINVAL, when date read from RTC is invalid for the pico's RTC.
RTC().datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))  # synch PR2040 rtc too


# log the error, blink the warning led, and go back to sleep
def halt(message):
    logging.error(message)
    leds_manager.set_warning_state(rtc, WARN_LED_BLINK)
    sleep()


# log the exception, blink the warning led, and go back to sleep
def exception(exc):
    import sys, io

    buf = io.StringIO()
    sys.print_exception(exc, buf)
    logging.exception("! " + buf.getvalue())
    leds_manager.set_warning_state(rtc, WARN_LED_BLINK)
    sleep()


# returns True if we've used up 90% of the internal filesystem
def low_disk_space():
    if not phew.remote_mount:  # os.statvfs doesn't exist on remote mounts
        return (os.statvfs(".")[3] / os.statvfs(".")[2]) < 0.1
    return False


# returns True if the rtc clock has been set recentlyd
def is_clock_set():
    # is the year on or before 2020?
    if rtc.datetime()[0] <= 2020:
        return False

    if helpers.file_exists("sync_time.txt"):
        now_str = helpers.datetime_string()
        now = helpers.timestamp(now_str)

        time_entries = []
        with open("sync_time.txt", "r") as timefile:
            time_entries = timefile.read().split("\n")

        # read the first line from the time file
        sync = now
        for entry in time_entries:
            if entry:
                sync = helpers.timestamp(entry)
                break

        seconds_since_sync = now - sync
        if seconds_since_sync >= 0:  # there's the rare chance of having a newer sync time than what the RTC reports
            try:
                if seconds_since_sync < (config.resync_frequency * 60 * 60):
                    return True

                logging.info(f"  - rtc has not been synched for {config.resync_frequency} hour(s)")
            except AttributeError:
                return True

    return False


# connect to wifi and attempt to fetch the current time from an ntp server
def sync_clock_from_ntp():
    from phew import ntp

    if not wifi_manager.connect():
        return False
    # TODO Fetch only does one attempt. Can also optionally set Pico RTC (do we want this?)
    timestamp = ntp.fetch()
    if not timestamp:
        logging.error("  - failed to fetch time from ntp server")
        return False

    # fixes an issue where sometimes the RTC would not pick up the new time
    i2c.writeto_mem(0x51, 0x00, b"\x10")  # reset the rtc so we can change the time
    rtc.datetime(timestamp)  # set the time on the rtc chip
    i2c.writeto_mem(0x51, 0x00, b"\x00")  # ensure rtc is running
    rtc.enable_timer_interrupt(False)

    # read back the RTC time to confirm it was updated successfully
    dt = rtc.datetime()
    if dt != timestamp[0:7]:
        logging.error("  - failed to update rtc")
        if helpers.file_exists("sync_time.txt"):
            os.remove("sync_time.txt")
        return False

    logging.info("  - rtc synched")

    # write out the sync time log
    with open("sync_time.txt", "w") as syncfile:
        syncfile.write("{0:04d}-{1:02d}-{2:02d}T{3:02d}:{4:02d}:{5:02d}Z".format(*timestamp))

    return True


leds_manager.set_warning_state(rtc, WARN_LED_OFF)


# returns the reason the board woke up from deep sleep
def get_wake_reason():
    import wakeup

    wake_reason = None
    if wakeup.get_gpio_state() & (1 << BUTTON_PIN):
        wake_reason = WAKE_REASON_BUTTON_PRESS
    elif wakeup.get_gpio_state() & (1 << RTC_ALARM_PIN):
        wake_reason = WAKE_REASON_RTC_ALARM
    # TODO Temporarily removing this as false reporting on non-camera boards
    # elif not external_trigger_pin.value():
    #  wake_reason = WAKE_REASON_EXTERNAL_TRIGGER
    elif vbus_present:
        wake_reason = WAKE_REASON_USB_POWERED
    return wake_reason


# convert a wake reason into it's name
def wake_reason_name(wake_reason):
    names = {
        None: "unknown",
        WAKE_REASON_PROVISION: "provisioning",
        WAKE_REASON_BUTTON_PRESS: "button",
        WAKE_REASON_RTC_ALARM: "rtc_alarm",
        WAKE_REASON_EXTERNAL_TRIGGER: "external_trigger",
        WAKE_REASON_RAIN_TRIGGER: "rain_sensor",
        WAKE_REASON_USB_POWERED: "usb_powered",
    }
    return names.get(wake_reason)


# get modules conected to qw/st port
def get_qwst_modules():
    modules = []
    if I2C_ADDR_LTR390 in i2c_devices:  # LTR390
        try:
            import enviro.qwst_modules.ltr390 as ltr390

            modules.append({"name": "LTR390", "include": ltr390, "address": I2C_ADDR_LTR390})
        except RuntimeError:
            pass
    if I2C_ADDR_SCD41 in i2c_devices:  # SCD41
        try:
            import enviro.qwst_modules.scd41 as scd41

            modules.append({"name": "SCD41", "include": scd41, "address": I2C_ADDR_SCD41})
        except RuntimeError:
            pass

    return modules


# get the readings from the on board sensors
def get_sensor_readings():
    seconds_since_last = 0
    now_str = helpers.datetime_string()
    if helpers.file_exists("last_time.txt"):
        now = helpers.timestamp(now_str)

        time_entries = []
        with open("last_time.txt", "r") as timefile:
            time_entries = timefile.read().split("\n")

        # read the first line from the time file
        last = now
        for entry in time_entries:
            if entry:
                last = helpers.timestamp(entry)
                break

        seconds_since_last = now - last
        logging.info(f"  - seconds since last reading: {seconds_since_last}")

    readings = get_board().get_sensor_readings(seconds_since_last, vbus_present)
    # append qw/st module readings to payload
    for module in get_qwst_modules():
        logging.info(f"> getting readings from module: {module['name']}")
        readings = readings | module["include"].get_readings(i2c, module["address"])

    # write out the last time log
    with open("last_time.txt", "w") as timefile:
        timefile.write(now_str)

    return readings


# save the provided readings into a todays readings data file
def save_reading(readings):
    # open todays reading file and save readings
    helpers.mkdir_safe("readings")
    readings_filename = f"readings/{helpers.datetime_file_string()}.txt"
    new_file = not helpers.file_exists(readings_filename)
    with open(readings_filename, "a") as f:
        if new_file:
            # new readings file so write out column headings first
            f.write("timestamp," + ",".join(readings.keys()) + "\r\n")

        # write sensor data
        row = [helpers.datetime_string()]
        for key in readings.keys():
            row.append(str(readings[key]))
        f.write(",".join(row) + "\r\n")


# normalize payload to sends to destination
def normalize_payload(readings):
    # fmt: off
    payload = {
        "nickname": config.nickname, 
        "timestamp": helpers.datetime_string(), 
        "firmware": ENVIRO_VERSION,
        "readings": readings, 
        "model": model, 
        "uid": helpers.uid(),
        "battery_voltage": None,
        "battery_percent": None,
    }
    # fmt: on

    if config.enable_battery_voltage and not vbus_present:
        try:
            logging.debug(f"> geting battery voltage")
            vbat_filtered = 0
            while vbat_filtered < 3.0 or vbat_filtered > 4.3:
                vbat_filtered = helpers.get_battery_voltage()
                time.sleep(0.5)
            payload["battery_voltage"] = vbat_filtered
            payload["battery_percent"] = helpers.get_battery_percent(vbat_filtered)
            logging.debug(f"> battery voltage: {payload['battery_voltage']}, percent: {payload['battery_percent']}")
        except Exception as e:
            logging.error("! unknown error to get battery voltage: {}".format(e))

    return payload


# save the provided readings into a cache file for future uploading
def cache_upload(readings):
    payload = normalize_payload(readings)
    uploads_filename = f"uploads/{helpers.datetime_file_string()}.json"
    helpers.mkdir_safe("uploads")
    with open(uploads_filename, "w") as upload_file:
        # json.dump(payload, upload_file) # TODO what it was changed to
        upload_file.write(ujson.dumps(payload))


# return the number of cached results waiting to be uploaded
def cached_upload_count():
    if config.upload_frequency == 1:
        return 0
    try:
        return len(os.listdir("uploads"))
    except OSError:
        return 0


# returns True if upload when reading
def is_upload_on_demand():
    return config.upload_frequency == 1


# returns True if we have more cached uploads than our config allows
def is_upload_needed():
    return cached_upload_count() >= config.upload_frequency


# upload the readings to a destination
def upload_readings(readings=None):
    if not wifi_manager.connect():
        logging.error(f"  - cannot upload readings, wifi connection failed")
        return False

    destination = config.destination
    secondary_destination = config.secondary_destination
    valid_secondary_destinations = [
        "mqtt",
        "wunderground",
    ]

    try:
        exec(f"import enviro.destinations.{destination}")
        destination_module = sys.modules[f"enviro.destinations.{destination}"]
        secondary_destination_module = None

        if secondary_destination in valid_secondary_destinations and secondary_destination != destination:
            exec(f"import enviro.destinations.{secondary_destination}")
            secondary_destination_module = sys.modules[f"enviro.destinations.{secondary_destination}"]

        destination_module.log_destination()

        jsons = []

        if readings is not None:
            payload = normalize_payload(readings)
            payload["wifi"] = wifi_manager.get_last_signal_strength()
            payload["file"] = None
            jsons.append(payload)
        else:
            for cache_file in os.ilistdir("uploads"):
                with open(f"uploads/{cache_file[0]}", "r") as upload_file:
                    payload = ujson.load(upload_file)
                    payload["wifi"] = wifi_manager.get_last_signal_strength()
                    payload["file"] = cache_file[0]
                    jsons.append(payload)

        for json in jsons:
            try:
                file_name = json["file"]
                status = destination_module.upload_reading(json)
                if status == UPLOAD_SUCCESS:
                    if file_name is not None:
                        os.remove(f"uploads/{file_name}")
                        logging.info(f"  - uploaded {file_name}")
                    else:
                        logging.info(f"  - uploaded readings on demand")

                elif status == UPLOAD_RATE_LIMITED and file_name is not None:
                    # write out that we want to attempt a reupload
                    with open("reattempt_upload.txt", "w") as attemptfile:
                        attemptfile.write("")

                    logging.info(f"  - cannot upload '{file_name}' - rate limited")
                    sleep(1)
                elif status == UPLOAD_LOST_SYNC and file_name is not None:
                    # remove the sync time file to trigger a resync on next boot
                    if helpers.file_exists("sync_time.txt"):
                        os.remove("sync_time.txt")

                    # write out that we want to attempt a reupload
                    with open("reattempt_upload.txt", "w") as attemptfile:
                        attemptfile.write("")

                    logging.info(f"  - cannot upload '{file_name}' - rtc has become out of sync")
                    sleep(1)
                elif status == UPLOAD_SKIP_FILE:
                    if file_name is not None:
                        logging.error(f"  ! cannot upload '{file_name}' to {destination}. Skipping file")
                    else:
                        logging.error(f"  ! cannot push reading to {destination}. Skipping reading")

                    leds_manager.set_warning_state(rtc, WARN_LED_BLINK)
                    continue
                else:
                    if file_name is not None:
                        logging.error(f"  ! cannot upload '{file_name}' to {destination}")
                    else:
                        logging.error(f"  ! cannot push reading to {destination}")
                    return False

                if secondary_destination is not None:
                    secondary_destination_module.log_destination()
                    if secondary_destination_module.upload_reading(json) == UPLOAD_SUCCESS:
                        if file_name is not None:
                            logging.error(f"  - Secondary destination upload success for {filename}")
                        else:
                            logging.error(f"  - Secondary destination uploaded readings on demand")

            except Exception as e:
                if file_name is not None:
                    logging.error(
                        "  ! exception when upload readings '{}' to {}, exp: {}".format(file_name, destination, e)
                    )
                else:
                    logging.error("  ! exception when uploadings to {}, exp: {}".format(destination, e))

    except ImportError:
        logging.error(f"! cannot find destination {destination}")
        return False

    finally:
        wifi_manager.disconnect()

    return True


# HASS Discovery
def hass_discovery():
    if not wifi_manager.connect():
        logging.error(f"! wifi connection failed")
        return False

    destination = config.destination
    try:
        exec(f"import enviro.destinations.{destination}")
        destination_module = sys.modules[f"enviro.destinations.{destination}"]
        destination_module.hass_discovery()
        helpers.update_config("hass_discovery_triggered", True)
    except ImportError:
        logging.error(f"! cannot find destination {destination}")
        return False
    except Exception as e:
        logging.error("! unknown error in setting HASS Discovery: {}".format(e))


# starts the program
def startup():
    import sys

    # write startup info into log file
    logging.info("> performing startup")
    logging.debug(f"  - running Enviro {ENVIRO_VERSION}, {sys.version.split('; ')[1]}")

    # get the reason we were woken up
    reason = get_wake_reason()

    # give each board a chance to perform any startup it needs
    # ===========================================================================
    board = get_board()
    if hasattr(board, "startup"):
        continue_startup = board.startup(reason)
        # put the board back to sleep if the startup doesn't need to continue
        # and the RTC has not triggered since we were awoken
        if not continue_startup and not rtc.read_alarm_flag():
            logging.debug("  - wake reason: trigger")
            sleep()

    # log the wake reason
    logging.info("  - wake reason:", wake_reason_name(reason))

    # also immediately turn on the LED to indicate that we're doing something
    logging.debug("  - turn on activity led")
    leds_manager.pulse_activity(0.5)

    # see if we were woken to attempt a reupload
    if helpers.file_exists("reattempt_upload.txt"):
        upload_count = cached_upload_count()
        if upload_count == 0:
            os.remove("reattempt_upload.txt")
            return

        logging.info(f"> {upload_count} cache file(s) still to upload")
        if not upload_readings():
            halt("! reading upload failed")

        os.remove("reattempt_upload.txt")

        # if it was the RTC that woke us, go to sleep until our next scheduled reading
        # otherwise continue with taking new readings etc
        # Note, this *may* result in a missed reading
        if reason == WAKE_REASON_RTC_ALARM:
            sleep()


# def sleep(time_override=None):
#     if time_override is not None:
#         logging.info(f"> going to sleep for {time_override} minute(s)")
#     else:
#         logging.info("> going to sleep")

#     # make sure the rtc flags are cleared before going back to sleep
#     logging.debug("  - clearing and disabling previous alarm")
#     rtc.clear_timer_flag()  # TODO this was removed from 0.0.8
#     rtc.clear_alarm_flag()

#     # set alarm to wake us up for next reading
#     dt = rtc.datetime()
#     hour, minute, second = dt[3:6]

#     # calculate how many minutes into the day we are
#     if time_override is not None:
#         minute += time_override
#     else:
#         # if the time is very close to the end of the minute, advance to the next minute
#         # this aims to fix the edge case where the board goes to sleep right as the RTC triggers, thus never waking up
#         if second > 55:
#             minute += 1
#         minute = math.floor(minute / config.reading_frequency) * config.reading_frequency
#         minute += config.reading_frequency

#     while minute >= 60:
#         minute -= 60
#         hour += 1
#     if hour >= 24:
#         hour -= 24
#     ampm = "am" if hour < 12 else "pm"

#     logging.info(f"  - setting alarm to wake at {hour:02}:{minute:02}{ampm}")

#     # sleep until next scheduled reading
#     rtc.set_alarm(0, minute, hour)
#     rtc.enable_alarm_interrupt(True)

#     # disable the vsys hold, causing us to turn off
#     logging.info("  - shutting down")
#     hold_vsys_en_pin.init(Pin.IN)

#     # if we're still awake it means power is coming from the USB port in which
#     # case we can't (and don't need to) sleep.
#     leds_manager.stop_activity()

#     # if running via mpremote/pyboard.py with a remote mount then we can't
#     # reset the board so just exist
#     if phew.remote_mount:
#         sys.exit()

#     # we'll wait here until the rtc timer triggers and then reset the board
#     logging.debug("  - on usb power (so can't shutdown). Halt and wait for alarm or user reset instead")
#     board = get_board()
#     while not rtc.read_alarm_flag():
#         if hasattr(board, "check_trigger"):
#             board.check_trigger()

#         # time.sleep(0.25)

#         if button_pin.value():  # allow button to force reset
#             break

#     logging.debug("  - reset")

#     # reset the board
#     machine.reset()


# finishs the program
def sleep(time_override=None):
    """
    Light sleep based on time.sleep instead of RTC alarm / power-off.

    - Uses config.reading_frequency (min) when time_override is None
    - While "sleeping", calls board.check_trigger() para continuar
      registrando chuva e permite sair pelo botão.
    """

    import enviro  # garante acesso a get_board

    board = get_board()

    if time_override is not None:
        minutes = time_override
        logging.info(f"> going to sleep for {minutes} minute(s)")
    else:
        minutes = config.reading_frequency
        logging.info(f"> going to sleep for {minutes} minute(s)")

    total_seconds = int(minutes * 60)

    # vamos só "apagar" a atividade e ficar em laço leve
    leds_manager.stop_activity()

    logging.debug(f"  - light sleep for {total_seconds} second(s)")

    step = 0.25  # resolução de 250 ms para checar sensor de chuva / botão
    steps = int(total_seconds / step)

    for _ in range(steps):
        # deixa a board.weather registrar chuva enquanto estamos "dormindo"
        if hasattr(board, "check_trigger"):
            try:
                board.check_trigger()
            except Exception as exc:
                logging.error(f"  ! error in board.check_trigger: {exc}")

        # botão pode interromper o sleep (por ex. pra reconfigurar)
        if button_pin.value():
            logging.info("  - sleep interrupted by button press")
            break

        time.sleep(step)

    logging.debug("  - sleep finished")
