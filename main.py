from time import sleep

sleep(0.5)

import enviro
import ota_light as ota

# Faz o startup normal UMA VEZ
try:
    enviro.startup()
except Exception as exc:
    enviro.exception(exc)

while True:
    try:
        enviro.leds_manager.pulse_activity(0.5)
        # garante que o relógio (RTC / NTP) está razoavelmente certo
        if not enviro.is_clock_set():
            enviro.logging.debug("> clock not set, synchronise from ntp server")
            if not enviro.sync_clock_from_ntp():
                # falhou NTP → loga e dorme um ciclo em vez de travar
                enviro.logging.error("! failed to synchronise clock, continuing with unsynced time")
        
        # test if has a ota update
        ota.check_and_update()

        # Add HASS Discovery command before taking new readings
        if (
            not enviro.config.hass_discovery_triggered
            and enviro.config.destination == "mqtt"
            and enviro.config.hass_discovery
        ):
            enviro.hass_discovery()
        else:
            enviro.logging.debug("> HASS discovery disabled or not applicable")

        # leitura de sensores
        enviro.logging.debug("> taking new reading")
        reading = enviro.get_sensor_readings()

        # upload / cache igual ao original
        if enviro.config.destination:
            if enviro.is_upload_on_demand():
                enviro.logging.debug("> uploading on demand")
                if not enviro.upload_readings(reading):
                    enviro.halt("! reading upload failed")
            else:
                enviro.logging.debug("> caching reading for upload")
                enviro.cache_upload(reading)

                if enviro.is_upload_needed():
                    if enviro.cached_upload_count() > 0:
                        enviro.logging.debug(f"> {enviro.cached_upload_count()} cache file(s) need uploading")

                    if not enviro.upload_readings():
                        enviro.halt("! reading upload failed")
                else:
                    enviro.logging.debug(f"> {enviro.cached_upload_count()} cache file(s) not being uploaded. ")
                    enviro.logging.debug(f"> Waiting until there are {enviro.config.upload_frequency} file(s)")
        else:
            enviro.logging.debug("> saving reading locally")
            enviro.save_reading(reading)

        # em vez de desligar + RTC, usamos o novo sleep baseado em time.sleep
        enviro.sleep()

    except Exception as exc:
        enviro.exception(exc)
        # pequena pausa antes de tentar o próximo ciclo
        sleep(5)
