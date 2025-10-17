
```markdown name=SDD_Apertus.md
```markdown
# Software Design Document — Apertus (Very High Level)

Version: 0.7  
Author: hoffmajf / Draft by Copilot  
Date: 2025-10-17

1. Overview
- Project name: Apertus
- Elevator pitch: Arduino Nano–based firmware to monitor and control a USAutomatic (Patriot control board) gate and integrate with Home Assistant via RFM69HCW ATC (915 MHz) radios bridged to MQTT by a local Gateway Nano.
- Primary goal: Safe, battery-backed gate control with state reporting, battery & solar telemetry, and reliable Home Assistant integration.

2. Constraints & choices
- Radio: RFM69HCW 915 MHz
- MCU: 5V Arduino Nano + Adafruit RFM69HCW breakout (handles level shift)
- Power: 12V lead-acid; ADC voltage divider
- Integration: Gateway Nano over USB + Python bridge -> MQTT -> Home Assistant

3. Top features
- Remote control (OPEN/CLOSE/STOP + LATCH/UNLATCH/TIMER_CLOSE)
- Telemetry: battery, solar, rssi, radio_temp, uptime
- Sensors: limit/photoeye/free-exit

4. Architecture & artifacts
- Gate node sketch: Apertus_Gate.ino
- Gateway sketch: Apertus_Gateway.ino
- Bridge: apertus_serial_mqtt_bridge.py
- Autodetect helper and systemd units for HA host
