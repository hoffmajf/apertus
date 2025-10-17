```markdown
# Apertus — Installation Instructions

This guide walks you step-by-step through installing the Apertus bridge and service on a Home Assistant host and flashing the Arduino sketches for Gate and Gateway nodes.

Assumptions
-----------
- You have two Arduino Nano boards (5V) with Adafruit RFM69HCW 915 MHz breakouts.
- You have a Home Assistant host (Linux) with access to an MQTT broker (Mosquitto or HA built-in).
- You have administrative access (sudo) on the host.

Paths used in this guide (change as needed)
- Project install directory: /opt/apertus
- Bridge script: /opt/apertus/apertus_serial_mqtt_bridge.py
- Detect helper: /usr/local/bin/apertus-detect-serial.py
- Env file: /etc/apertus/apertus.env
- Systemd units: /etc/systemd/system/apertus-bridge.service and /etc/systemd/system/apertus-detect.service
- Service user: homeassistant (change if your HA uses a different user)

1) Prepare host directories and files
------------------------------------
sudo mkdir -p /opt/apertus
sudo chown homeassistant:homeassistant /opt/apertus
sudo chmod 750 /opt/apertus

sudo mkdir -p /etc/apertus
sudo chown root:root /etc/apertus
sudo chmod 750 /etc/apertus

2) Copy scripts to host
-----------------------
Place the following files onto the host:

- /opt/apertus/apertus_serial_mqtt_bridge.py  (from repo)
- /usr/local/bin/apertus-detect-serial.py
- (optional) discovery JSON files for manual publishing

Set permissions:
sudo chown homeassistant:homeassistant /opt/apertus/apertus_serial_mqtt_bridge.py
sudo chmod 750 /opt/apertus/apertus_serial_mqtt_bridge.py

sudo chmod +x /usr/local/bin/apertus-detect-serial.py
sudo chown root:root /usr/local/bin/apertus-detect-serial.py

3) Create Python virtual environment & install deps
---------------------------------------------------
sudo -u homeassistant python3 -m venv /opt/apertus/venv
sudo -u homeassistant /opt/apertus/venv/bin/pip install --upgrade pip
sudo -u homeassistant /opt/apertus/venv/bin/pip install paho-mqtt pyserial

4) Create initial env file (will be overwritten by detect helper if it finds a gateway)
-------------------------------------------------------------------------------------
Create `/etc/apertus/apertus.env`:
sudo tee /etc/apertus/apertus.env > /dev/null <<'EOF'
APERTUS_SERIAL="/dev/ttyUSB0"
APERTUS_BAUD=115200
APERTUS_MQTT_HOST=localhost
APERTUS_MQTT_PORT=1883
APERTUS_MQTT_USER=
APERTUS_MQTT_PASS=
EOF

Set permissions:
sudo chmod 640 /etc/apertus/apertus.env
sudo chown root:root /etc/apertus/apertus.env

5) Install systemd units
------------------------
Copy these units to `/etc/systemd/system/`:

- `/etc/systemd/system/apertus-detect.service` (runs detect helper once at boot)
- `/etc/systemd/system/apertus-bridge.service` (venv bridged service)

Example commands (adjust if you placed files elsewhere):
sudo cp /path/to/apertus-detect-serial.py /usr/local/bin/apertus-detect-serial.py
sudo chmod +x /usr/local/bin/apertus-detect-serial.py

sudo cp /path/to/apertus-detect.service /etc/systemd/system/apertus-detect.service
sudo cp /path/to/apertus-bridge.service /etc/systemd/system/apertus-bridge.service

Reload systemd:
sudo systemctl daemon-reload

Enable and start detect service (it creates/updates /etc/apertus/apertus.env)
sudo systemctl enable --now apertus-detect.service
Check status/logs:
sudo journalctl -u apertus-detect -f

Enable and start the bridge service:
sudo systemctl enable --now apertus-bridge.service
Check logs:
sudo journalctl -u apertus-bridge -f

6) Flash the Arduino sketches
-----------------------------
Use Arduino IDE, PlatformIO, or arduino-cli.

Important: set correct AES key in both sketches BEFORE flashing.

Example arduino-cli (adjust fqbn for your Nano):
arduino-cli compile --fqbn arduino:avr:nano Apertus_Gateway
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano Apertus_Gateway

Repeat for Apertus_Gate and upload to gate Nano.

7) Verify end-to-end
--------------------
- After Gateway boots, it prints ready marker over serial: `{"gateway":"apertus_ready"}`.
- The detect helper should detect and write `/etc/apertus/apertus.env`.
- The bridge service should read that env and connect to the serial device and MQTT.
- Check MQTT telemetry:
  mosquitto_sub -h localhost -t 'apertus/+/telemetry' -v
- Trigger a command from HA or command line:
  mosquitto_pub -h localhost -t 'apertus/20/cmd' -m 'OPEN'

8) Home Assistant integration
-----------------------------
- The bridge publishes MQTT Discovery messages (retained). In Home Assistant, ensure the MQTT integration is configured.
- Accepted entities will appear as a Cover (gate) and sensors (battery, solar, RSSI, radio temp).
- If discovery doesn't appear: verify MQTT credentials, and that discovery is enabled in HA (Integration > MQTT > Enable discovery).

9) Calibrate ADC & battery percent
----------------------------------
- Measure voltage at ADC with a multimeter and compare with telemetry from HA.
- Adjust `BATTERY_DIVIDER_FACTOR` in the Gate sketch to match your resistor divider.
- Update BATTERY_VOLTS_MIN / MAX to match your 12V lead‑acid chemistry.

10) Optional: autodetect timer (re-run detect periodically)
----------------------------------------------------------
If you unplug/replug the Gateway you might want periodic auto-detect. You can:
- Create a systemd timer or cron job that runs `/usr/local/bin/apertus-detect-serial.py` periodically (e.g., every 5 minutes).

11) Troubleshooting checklist
-----------------------------
- No ready marker: open Serial Monitor on Gateway Nano at 115200.
- Bridge not connecting: check /etc/apertus/apertus.env values and file permissions.
- MQTT messages not visible: verify broker connectivity/logs and use mosquitto_sub to debug.
- Radio not communicating: confirm both RFM69 modules are 915 MHz, same net/group/keys, and antennas connected.

12) Security & Production notes
-------------------------------
- Replace AES key with a secure, unique 16‑byte key; do not commit to a public repo.
- Restrict MQTT permissions for the bridge user (MQTT username/ACLs).
- Protect /etc/apertus/apertus.env (contains MQTT credentials if set).
- Consider adding serial authentication or physical protections if the host is untrusted.

13) Want help wiring J8?
------------------------
If you provide Patriot J8 textual pin mapping or allow me to inspect your photos and confirm pin labels, I will annotate the Gate sketch pin constants with exact J8 wiring and provide a wiring diagram. Always verify with a DMM before connecting.

14) Uninstall
-------------
To remove service and files:
sudo systemctl disable --now apertus-bridge.service apertus-detect.service
sudo rm /etc/systemd/system/apertus-bridge.service /etc/systemd/system/apertus-detect.service
sudo rm /usr/local/bin/apertus-detect-serial.py
sudo rm -rf /opt/apertus
sudo rm -rf /etc/apertus

Support & next steps
--------------------
If you want, I can:
- Produce a systemd timer to re-run the autodetect helper at intervals.
- Generate a Home Assistant add-on (if you run HA OS/ Supervised) that bundles the bridge.
- Create a wiring diagram and BOM once the Patriot J8 pin mapping is confirmed.

Enjoy Apertus — let me know if you want the add-on or wiring diagram next.