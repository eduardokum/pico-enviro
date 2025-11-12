from machine import Pin, PWM, Timer
import time
import math

from pcf85063a import PCF85063A  # type: ignore
from enviro.constants import (
    ACTIVITY_LED_PIN,
    WARN_LED_OFF,
    WARN_LED_ON,
    WARN_LED_BLINK,
)


class LedManager:
    def __init__(self, activity_pin=ACTIVITY_LED_PIN, pwm_freq=1000):
        # Configure activity LED as PWM
        self.activity_pwm = PWM(Pin(activity_pin))
        self.activity_pwm.freq(pwm_freq)
        self.activity_pwm.duty_u16(0)

        # Timer used for pulsing effect
        self.activity_timer = Timer(-1)
        self.activity_pulse_speed_hz = 1

    def _gamma_correct(self, brightness):
        """Apply gamma correction (gamma 2.8) and clamp to 0–100%."""
        brightness = max(0, min(100, brightness))
        return int(pow(brightness / 100.0, 2.8) * 65535.0 + 0.5)

    # ===== Activity LED =====

    def set_activity_led(self, brightness):
        """Set fixed brightness for activity LED (0–100%)."""
        value = self._gamma_correct(brightness)
        self.activity_pwm.duty_u16(value)

    def _activity_callback(self, timer):
        """Timer callback to update pulsing animation."""
        # Same sinusoid used no código original:
        # brightness = sin(t) * 40 + 60  -> faixa ~20% a ~100%
        brightness = (math.sin(time.ticks_ms() * math.pi * 2 / (1000 / self.activity_pulse_speed_hz)) * 40) + 60
        value = self._gamma_correct(brightness)
        self.activity_pwm.duty_u16(value)

    def pulse_activity(self, speed_hz=1.0):
        """Put activity LED into pulsing mode."""
        self.activity_pulse_speed_hz = speed_hz
        self.activity_timer.deinit()
        self.activity_timer.init(period=50, mode=Timer.PERIODIC, callback=self._activity_callback)

    def stop_activity(self):
        """Turn off activity LED and stop any running animation."""
        self.activity_timer.deinit()
        self.activity_pwm.duty_u16(0)

    # ===== Warning LED (via RTC clock output) =====
    def set_warning_state(self, rtc, state):
        """Set warning LED state (OFF, ON, BLINK)."""
        if state == WARN_LED_OFF:
            rtc.set_clock_output(PCF85063A.CLOCK_OUT_OFF)
        elif state == WARN_LED_ON:
            rtc.set_clock_output(PCF85063A.CLOCK_OUT_1024HZ)
        elif state == WARN_LED_BLINK:
            rtc.set_clock_output(PCF85063A.CLOCK_OUT_1HZ)
