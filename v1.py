"""
Acoustic Predictive Maintenance Prototype (optimized)
Raspberry Pi Pico 2 + MicroPython (MicroPico / VS Code)

Hardware: mic amp on GP26, 2x 8-LED WS2812B strips, buzzer on GP18
Method:   peak-to-peak amplitude over a ~50 ms window (no FFT)
Debounce: 3 consecutive readings on the same side before the state changes
Outputs:  VU bar (green -> yellow -> red), status strip (green/red), buzzer
"""

from machine import Pin, ADC, PWM
from micropython import const
from neopixel import NeoPixel
import time

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

# --- Sampling: 200 readings x ~250 us apart = ~50 ms window ---
SAMPLES_PER_WIN  = const(200)
SAMPLE_PERIOD_US = const(250)

# --- Thresholds (ADC units, 0-65535). Tune these by hand. ---
LOW_THRESHOLD  = const(8000)
HIGH_THRESHOLD = const(45000)
DEBOUNCE_COUNT = const(3)

# --- Strip sizes ---
VU_NUM_LEDS     = const(8)
STATUS_NUM_LEDS = const(8)

# --- VU-meter range (bar is full at the high threshold) ---
VU_MIN  = const(2000)
VU_MAX  = const(HIGH_THRESHOLD)
VU_SPAN = const(VU_MAX - VU_MIN)

# --- Pins (GPIO numbers, not physical pin numbers) ---
ADC_PIN        = 26     # GP26 = ADC0
VU_PIN         = 2
STATUS_PIN     = 3
BUZZER_PIN     = 18
BUZZER_FREQ_HZ = 2700

# --- Brightness: 0-255 (255 = full). Lower is easier on the eyes. ---
BRIGHTNESS = const(30)

def dim(colour):
    """Scale an (R, G, B) colour down by BRIGHTNESS."""
    return (colour[0] * BRIGHTNESS // 255,
            colour[1] * BRIGHTNESS // 255,
            colour[2] * BRIGHTNESS // 255)

# --- Colours (R, G, B) ---
GREEN  = dim((0, 255, 0))
YELLOW = dim((255, 180, 0))
RED    = dim((255, 0, 0))
OFF    = (0, 0, 0)

# Colour of each VU LED: 4 green, 2 yellow, 2 red
VU_COLOURS = (GREEN, GREEN, GREEN, GREEN, YELLOW, YELLOW, RED, RED)

# ------------------------------------------------------------------
# HARDWARE INIT
# ------------------------------------------------------------------

adc          = ADC(Pin(ADC_PIN))
vu_strip     = NeoPixel(Pin(VU_PIN), VU_NUM_LEDS)
status_strip = NeoPixel(Pin(STATUS_PIN), STATUS_NUM_LEDS)

buzzer = PWM(Pin(BUZZER_PIN))
buzzer.freq(BUZZER_FREQ_HZ)
buzzer.duty_u16(0)      # silent

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def measure_peak_to_peak():
    """Read the mic SAMPLES_PER_WIN times and return highest - lowest.

    The short sleep between readings stretches the window to ~50 ms so
    it covers low-frequency hum (a 50 Hz hum repeats every 20 ms).
    """
    lowest  = 65535
    highest = 0
    for _ in range(SAMPLES_PER_WIN):
        v = adc.read_u16()
        if v < lowest:
            lowest = v
        if v > highest:
            highest = v
        time.sleep_us(SAMPLE_PERIOD_US)
    return highest - lowest


vu_level = -1   # level currently drawn (-1 = nothing drawn yet)

def update_vu_meter(p2p):
    """Light LEDs in proportion to p2p. Rises instantly, falls 1 LED per call."""
    global vu_level

    if p2p <= VU_MIN:
        target = 0
    else:
        target = min((p2p - VU_MIN) * VU_NUM_LEDS // VU_SPAN, VU_NUM_LEDS)

    if target >= vu_level:
        level = target
    else:
        level = vu_level - 1

    if level == vu_level:
        return          # nothing changed, skip the redraw

    for i in range(VU_NUM_LEDS):
        vu_strip[i] = VU_COLOURS[i] if i < level else OFF
    vu_strip.write()
    vu_level = level


def set_status(alarm):
    """Whole status strip red on alarm, green otherwise."""
    status_strip.fill(RED if alarm else GREEN)
    status_strip.write()


def set_buzzer(on):
    buzzer.duty_u16(30000 if on else 0)


def startup_self_test():
    """Quick sweep so you can confirm the wiring before it starts."""
    for i in range(VU_NUM_LEDS):
        vu_strip[i] = GREEN
        vu_strip.write()
        time.sleep_ms(40)
    for i in range(STATUS_NUM_LEDS):
        status_strip[i] = GREEN
        status_strip.write()
        time.sleep_ms(40)

    time.sleep_ms(200)

    vu_strip.fill(OFF)
    vu_strip.write()
    status_strip.fill(OFF)
    status_strip.write()

# ------------------------------------------------------------------
# MAIN LOOP
# ------------------------------------------------------------------

def main():
    print("Acoustic predictive maintenance prototype started.")
    startup_self_test()
    set_status(False)           # start green

    alarm        = False
    last_reading = 0            # 1 = too loud, -1 = too quiet, 0 = normal
    streak       = 0            # how many times in a row we saw last_reading

    while True:
        p2p = measure_peak_to_peak()
        update_vu_meter(p2p)

        if p2p > HIGH_THRESHOLD:
            reading = 1
        elif p2p < LOW_THRESHOLD:
            reading = -1
        else:
            reading = 0

        # Debounce: count identical readings in a row
        if reading == last_reading:
            streak += 1
        else:
            last_reading = reading
            streak = 1

        # Only change state after DEBOUNCE_COUNT identical readings
        if streak >= DEBOUNCE_COUNT:
            should_alarm = (reading != 0)
            if should_alarm != alarm:
                alarm = should_alarm
                set_buzzer(alarm)
                set_status(alarm)
                if alarm:
                    print("[ALARM] p2p =", p2p, "HIGH" if reading == 1 else "LOW")
                else:
                    print("[OK] p2p =", p2p)

        time.sleep_ms(20)


if __name__ == "__main__":
    main()