```markdown
# Apertus — README

Version: 0.7  
Author: hoffmajf / Draft by Copilot  
Date: 2025-10-17

Short description
-----------------
Apertus is a small Arduino‑based gate controller and telemetry node that integrates a USAutomatic (Patriot) gate controller with Home Assistant using RFM69HCW (915 MHz) radios. A Gateway Arduino (USB) bridges radio ↔ USB serial; a Python bridge on the Home Assistant host converts serial JSON to MQTT and publishes Home Assistant MQTT Discovery payloads.

This repository contains:
- Apertus Gate sketch (Apertus_Gate.ino) — Node that runs on the gate Arduino Nano.
- Apertus Gateway sketch (Apertus_Gateway.ino) — USB-serial RFM69 bridge.
- apertus_serial_mqtt_bridge.py — Python serial→MQTT bridge for HA.
- apertus-detect-serial.py — serial autodetect helper (writes /etc/apertus/apertus.env).
- systemd service files and sample discovery JSON payloads (examples provided in docs).
- SDD and implementation notes (see the SDD file).

Key features
------------
- Remote control: OPEN / CLOSE / STOP / LATCH / UNLATCH / TIMER_CLOSE commands.
- Telemetry: battery_voltage, battery_pct, solar_voltage, charging, rssi, radio_temp_c, uptime_s.
- Board sensors reported: limit_open, limit_closed, photoeye_blocked, free_exit.
- Low-power considerations (placeholders; you must add MCU + radio sleep for battery life).
- Uses LowPowerLab RFM69 library with RFM69HCW ATC modules (915 MHz).
- Gateway Arduino connects over USB to Home Assistant host — no Raspberry Pi required.

Safety & wiring notice (read first)
-----------------------------------
- The Patriot (USAutomatic) control board provides onboard safety (photoeyes, free-exit, etc.). Apertus reports those signals — it does not replace board safety.
- DO NOT connect MCU GPIOs directly to the Patriot control board. Emulate dry-contact closures using optocouplers or small relays so the control board sees a passive contact closure.
- Verify J8 pin mappings on the Patriot board before wiring. If you are unsure, stop and get the Patriot J8 pin documentation.
- Work with low voltages and isolation practices: use flyback diodes, transients protection, and proper power decoupling.
- Replace the placeholder AES key in the sketches before production.

Quick start (hardware)
----------------------
Minimum hardware:
- Arduino Nano (5V) for Gate node and another Nano for Gateway (both with Adafruit RFM69HCW breakout that includes level shifting).
- Adafruit RFM69HCW ATC 915 MHz breakout(s) (one on node, one on gateway).
- 12 V lead-acid battery for gate power and voltage divider to read battery via ADC.
- Optocouplers or relays for dry-contact emulation to Patriot J8.
- Wires, antenna for 915 MHz (as supplied by RFM69 module), basic tools.

High-level wiring:
- Gate node: connect RFM69 breakout SPI pins to Nano (MOSI D11, MISO D12, SCK D13, CS D10, DIO0 to D2). Provide 3.3V to the radio (breakout handles level‑shift).
- Gate actuators: wire optocoupler/relay contacts to emulate momentary dry-contact closures to the Patriot J8 control inputs (OPEN / CLOSE / LATCH / UNLATCH / TIMER_CLOSE).
- Gate sensors: wire Patriot J8 status outputs (limit switches, photoeye, free-exit) to Nano inputs via appropriate level conditioning (use INPUT_PULLUP and treat signals as active-low by default).
- Gateway node: RFM69 breakout connected to Nano SPI, Gateway Nano USB → Home Assistant host.

Flashing the sketches
---------------------
You can use the Arduino IDE, PlatformIO or arduino-cli. Replace the AES key before building.

Arduino IDE:
1. Open `Apertus_Gate.ino` and `Apertus_Gateway.ino` in separate IDE windows.
2. Select board: "Arduino Nano" (match your variant: ATmega328P 5V/16MHz).
3. Select correct serial port and upload to each Nano.

arduino-cli (example)
- Install arduino-cli, set up the core, then:

  # compile (adjust fqbn for your Nano variant)
  arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 Apertus_Gate

  # upload (update /dev/ttyUSB0 to your port)
  arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano:cpu=atmega328 Apertus_Gate

PlatformIO (in VS Code)
- Create a PlatformIO project for an ATmega328P Nano, copy code, build & upload.

Important compile-time notes:
- Replace the example AES key string in both sketches with a 16‑byte secret:
    const char RF_AES_KEY[16] = "YOUR_16_BYTE_KEY";
- Set RF node IDs and network ID as desired (default gateway=10, gate node=20, net=100).
- Confirm RF69 library API compatibility; examples use LowPowerLab's RFM69 library functions (rf69.initialize, rf69.sendWithRetry, rf69.receiveDone, rf69.DATA, rf69.DATALEN, rf69.SENDERID).

Python bridge — install and run (Home Assistant host)
-----------------------------------------------------
This bridge reads JSON lines from the Gateway Nano serial and publishes MQTT topics under the `apertus/<nodeid>/...` prefix. It also subscribes to `apertus/+/cmd` to forward commands to the Gateway.

1. Place the bridge script:
   - Copy `apertus_serial_mqtt_bridge.py` to `/opt/apertus/apertus_serial_mqtt_bridge.py`.

2. Create a Python venv and install deps (recommended):
   sudo mkdir -p /opt/apertus
   sudo chown homeassistant:homeassistant /opt/apertus
   sudo -u homeassistant python3 -m venv /opt/apertus/venv
   sudo -u homeassistant /opt/apertus/venv/bin/pip install --upgrade pip
   sudo -u homeassistant /opt/apertus/venv/bin/pip install paho-mqtt pyserial

3. Configuration:
   - The service reads `/etc/apertus/apertus.env` (APERTUS_SERIAL, APERTUS_BAUD, APERTUS_MQTT_HOST, APERTUS_MQTT_PORT, APERTUS_MQTT_USER, APERTUS_MQTT_PASS).
   - You can write that file manually or use the `apertus-detect-serial.py` helper to auto-detect the Gateway device.

4. Start the bridge via systemd (see INSTALLATION.md for automated steps) or run manually for testing:
   /opt/apertus/venv/bin/python /opt/apertus/apertus_serial_mqtt_bridge.py --serial /dev/ttyUSB0 --baud 115200 --mqtt-host localhost --mqtt-port 1883

Verify topics with mosquitto_sub (example):
- Subscribe to telemetry:
  mosquitto_sub -t 'apertus/+/telemetry' -v
- Send a command to node 20:
  mosquitto_pub -t 'apertus/20/cmd' -m 'OPEN'

Home Assistant integration
--------------------------
The Python bridge publishes MQTT Discovery payloads (retained) automatically for each discovered node. If your HA MQTT integration is configured correctly, devices should appear automatically.

Systemd service & autodetect (recommended)
------------------------------------------
The project includes:
- `/etc/systemd/system/apertus-bridge.service` — runs the Python bridge using venv and reads config from `/etc/apertus/apertus.env`.
- `/usr/local/bin/apertus-detect-serial.py` — probe script that scans `/dev/ttyUSB*` and `/dev/ttyACM*` and writes `/etc/apertus/apertus.env` with detected serial device.
- `/etc/systemd/system/apertus-detect.service` — runs the detect helper at boot.

Use the venv-aware service (preferred) — see INSTALLATION.md for full commands to set up venv, copy files, enable services, and check status.

Telemetry topics summary
------------------------
Base prefix: `apertus/<nodeid>/...`

Main topics produced by the bridge:
- apertus/<nodeid>/telemetry — full JSON (non-retained)
- apertus/<nodeid>/state — gate state (open/closed/moving)
- apertus/<nodeid>/battery_voltage — V
- apertus/<nodeid>/battery_pct — %
- apertus/<nodeid>/solar_voltage — V
- apertus/<nodeid>/charging — 1/0 (simple heuristic)
- apertus/<nodeid>/rssi — dBm
- apertus/<nodeid>/radio_temp_c — Celsius
- apertus/<nodeid>/uptime_s — seconds
- apertus/<nodeid>/photoeye_blocked — 1/0
- apertus/<nodeid>/free_exit — 1/0

Retention rules (recommended)
- Discovery payloads: retained = true (bridge publishes retained).
- Telemetry topics: retained = false (avoid stale state after node offline).
- Alerts (optional): retained = true if you want last-known alarms preserved after broker restarts.

Testing & verification
----------------------
1. Bench test the Gate node with the Patriot board disconnected: verify telemetry JSON shows up on Gateway serial (`Serial Monitor`) and via MQTT when bridge is running.
2. Connect actuators via optocouplers/relays to Patriot J8 and verify emulated dry-contact pulses operate as expected before installing permanently.
3. Test commands: publish to `apertus/<nodeid>/cmd` and confirm the Gate node receives and responds (ACK) and telemetry updates.
4. Field test range: test RFM69 communications at installation distance, verify RSSI, adjust TX power if necessary.
5. Power tests: measure battery consumption for the duty cycle you expect; implement MCU + radio sleep to reach required battery life.

Troubleshooting
---------------
- No serial output from gateway: confirm correct COM/tty, baud 115200, and that the Gateway sketch prints the ready marker `{"gateway":"apertus_ready"}` on boot.
- No MQTT messages: confirm Python bridge is running, correct serial device, MQTT broker reachable, and topic subscriptions are correct.
- Telemetry values wrong: calibrate ADC dividerFactor constants in the sketch; confirm ADC reference voltage (5V Nano assumed), resistor values, and add offset calibration.
- Radio comms unreliable: check antenna and module frequency (915 MHz), gateway/node parity, and physical placement. Use RSSI to diagnose.

Files & naming
--------------
- Apertus_Gate.ino
- Apertus_Gateway.ino
- apertus_serial_mqtt_bridge.py
- apertus-detect-serial.py
- /etc/apertus/apertus.env (created by detect helper or manually)
- systemd units: apertus-bridge.service, apertus-detect.service (see INSTALLATION.md)

License
-------
Include your preferred license. No license included by default.

Contributing
------------
Open issues or PRs with configuration improvements, improved power management patches, or hardware BOM updates. Also provide Patriot J8 pin mappings so wiring can be documented in the repo.

Contact
-------
Owner: hoffmajf
```