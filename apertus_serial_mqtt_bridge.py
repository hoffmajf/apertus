#!/usr/bin/env python3
"""
apertus_serial_mqtt_bridge.py

Serial -> MQTT bridge for Apertus Gateway Nano.

- Reads JSON lines from serial (gateway outputs lines like {"src":20,"rssi":-72,"payload":"{...}"})
- Publishes to MQTT topics under 'apertus/<nodeid>/...'
- Subscribes to apertus/+/cmd to forward commands to the Gateway serial in format:
    TO:<nodeid>:<payload>\n
- Emits Home Assistant MQTT Discovery payloads (retained) for cover and key sensors.
"""

import argparse
import json
import logging
import time
import paho.mqtt.client as mqtt
import serial

# Configuration (update as needed)
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUD = 115200
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USER = None
MQTT_PASS = None
MQTT_BASE = "apertus"
HA_DISC_PREFIX = "homeassistant"
RETAIN_DISCOVERY = True

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("apertus-bridge")

def safe_json_loads(s):
    try:
        return json.loads(s)
    except Exception:
        return None

class SerialMqttBridge:
    def __init__(self, serial_port, serial_baud, mqtt_cfg):
        self.serial_port = serial_port
        self.serial_baud = serial_baud
        self.mqtt_cfg = mqtt_cfg
        self.ser = None
        self.mqtt = None
        self.known_nodes = set()

    def open_serial(self):
        while True:
            try:
                self.ser = serial.Serial(self.serial_port, baudrate=self.serial_baud, timeout=1.0)
                log.info("Opened serial port %s @ %d", self.serial_port, self.serial_baud)
                return
            except Exception as e:
                log.error("Cannot open serial port %s: %s. Retrying in 5s...", self.serial_port, e)
                time.sleep(5)

    def start_mqtt(self):
        self.mqtt = mqtt.Client()
        if self.mqtt_cfg.get("user"):
            self.mqtt.username_pw_set(self.mqtt_cfg["user"], self.mqtt_cfg["pass"])
        self.mqtt.on_connect = self.on_mqtt_connect
        self.mqtt.on_message = self.on_mqtt_message
        while True:
            try:
                self.mqtt.connect(self.mqtt_cfg["host"], self.mqtt_cfg["port"])
                self.mqtt.loop_start()
                log.info("Connected to MQTT broker %s:%d", self.mqtt_cfg["host"], self.mqtt_cfg["port"])
                return
            except Exception as e:
                log.error("MQTT connect failed: %s. Retrying in 5s...", e)
                time.sleep(5)

    def on_mqtt_connect(self, client, userdata, flags, rc):
        topic = f"{MQTT_BASE}/+/cmd"
        client.subscribe(topic)
        log.info("Subscribed to %s", topic)

    def on_mqtt_message(self, client, userdata, msg):
        topic_parts = msg.topic.split('/')
        if len(topic_parts) >= 3 and topic_parts[0] == MQTT_BASE and topic_parts[2] == "cmd":
            nodeid = topic_parts[1]
            payload = msg.payload.decode('utf-8')
            self.send_serial_command(nodeid, payload)

    def send_serial_command(self, nodeid, payload):
        line = f"TO:{nodeid}:{payload}\n"
        try:
            if self.ser and self.ser.is_open:
                self.ser.write(line.encode('utf-8'))
                log.info("WROTE to serial: %s", line.strip())
            else:
                log.warning("Serial not open, cannot send: %s", line.strip())
        except Exception as e:
            log.error("Failed writing to serial: %s", e)

    def publish_discovery(self, nodeid):
        node_name = f"Apertus_{nodeid}"
        # Cover discovery
        cover_topic = f"{HA_DISC_PREFIX}/cover/apertus_{nodeid}/config"
        cover_payload = {
            "name": node_name,
            "uniq_id": f"apertus_cover_{nodeid}",
            "command_topic": f"{MQTT_BASE}/{nodeid}/cmd",
            "state_topic": f"{MQTT_BASE}/{nodeid}/state",
            "payload_open": "OPEN",
            "payload_close": "CLOSE",
            "payload_stop": "STOP",
            "qos": 1,
            "device": {"identifiers": [f"apertus_{nodeid}"], "name": node_name}
        }
        self.mqtt.publish(cover_topic, json.dumps(cover_payload), retain=RETAIN_DISCOVERY)

        # Battery sensor
        bat_topic = f"{HA_DISC_PREFIX}/sensor/apertus_{nodeid}_battery/config"
        bat_payload = {
            "name": f"{node_name} Battery",
            "state_topic": f"{MQTT_BASE}/{nodeid}/battery_voltage",
            "unit_of_measurement": "V",
            "uniq_id": f"apertus_batt_{nodeid}",
            "device": {"identifiers": [f"apertus_{nodeid}"], "name": node_name}
        }
        self.mqtt.publish(bat_topic, json.dumps(bat_payload), retain=RETAIN_DISCOVERY)

        # Additional sensors: solar, rssi, radio_temp, battery_pct, photoeye
        solar_topic = f"{HA_DISC_PREFIX}/sensor/apertus_{nodeid}_solar/config"
        solar_payload = {
            "name": f"{node_name} Solar",
            "state_topic": f"{MQTT_BASE}/{nodeid}/solar_voltage",
            "unit_of_measurement": "V",
            "uniq_id": f"apertus_solar_{nodeid}",
            "device": {"identifiers": [f"apertus_{nodeid}"], "name": node_name}
        }
        self.mqtt.publish(solar_topic, json.dumps(solar_payload), retain=RETAIN_DISCOVERY)

        rssi_topic = f"{HA_DISC_PREFIX}/sensor/apertus_{nodeid}_rssi/config"
        rssi_payload = {
            "name": f"{node_name} RSSI",
            "state_topic": f"{MQTT_BASE}/{nodeid}/rssi",
            "unit_of_measurement": "dBm",
            "uniq_id": f"apertus_rssi_{nodeid}",
            "device": {"identifiers": [f"apertus_{nodeid}"], "name": node_name}
        }
        self.mqtt.publish(rssi_topic, json.dumps(rssi_payload), retain=RETAIN_DISCOVERY)

        rt_topic = f"{HA_DISC_PREFIX}/sensor/apertus_{nodeid}_radio_temp/config"
        rt_payload = {
            "name": f"{node_name} Radio Temp",
            "state_topic": f"{MQTT_BASE}/{nodeid}/radio_temp_c",
            "unit_of_measurement": "°C",
            "uniq_id": f"apertus_radiotemp_{nodeid}",
            "device": {"identifiers": [f"apertus_{nodeid}"], "name": node_name}
        }
        self.mqtt.publish(rt_topic, json.dumps(rt_payload), retain=RETAIN_DISCOVERY)

        batpct_topic = f"{HA_DISC_PREFIX}/sensor/apertus_{nodeid}_battery_pct/config"
        batpct_payload = {
            "name": f"{node_name} Battery %",
            "state_topic": f"{MQTT_BASE}/{nodeid}/battery_pct",
            "unit_of_measurement": "%",
            "uniq_id": f"apertus_battpct_{nodeid}",
            "device": {"identifiers": [f"apertus_{nodeid}"], "name": node_name}
        }
        self.mqtt.publish(batpct_topic, json.dumps(batpct_payload), retain=RETAIN_DISCOVERY)

        photo_topic = f"{HA_DISC_PREFIX}/binary_sensor/apertus_{nodeid}_photo/config"
        photo_payload = {
            "name": f"{node_name} Photoeye Blocked",
            "state_topic": f"{MQTT_BASE}/{nodeid}/photoeye_blocked",
            "payload_on": "1",
            "payload_off": "0",
            "device_class": "safety",
            "uniq_id": f"apertus_photo_{nodeid}",
            "device": {"identifiers": [f"apertus_{nodeid}"], "name": node_name}
        }
        self.mqtt.publish(photo_topic, json.dumps(photo_payload), retain=RETAIN_DISCOVERY)

    def handle_incoming_line(self, line):
        line = line.strip()
        if not line:
            return
        try:
            obj = json.loads(line)
        except Exception:
            log.debug("Serial non-json: %s", line)
            return

        if obj.get("gateway") == "apertus_ready":
            log.info("Gateway reported ready")
            return

        src = obj.get("src")
        if src is None:
            log.debug("No src in serial JSON: %s", obj)
            return
        src = str(src)

        payload_raw = obj.get("payload")
        parsed_payload = None
        if isinstance(payload_raw, str):
            parsed_payload = safe_json_loads(payload_raw)
            if parsed_payload is None:
                parsed_payload = {"raw": payload_raw}
        elif isinstance(payload_raw, dict):
            parsed_payload = payload_raw
        else:
            parsed_payload = {"raw": str(payload_raw)}

        combined = {}
        if isinstance(parsed_payload, dict):
            combined.update(parsed_payload)
        if "rssi" not in combined and "rssi" in obj:
            combined["rssi"] = obj.get("rssi")
        if "src" not in combined:
            combined["src"] = src

        telemetry_topic = f"{MQTT_BASE}/{src}/telemetry"
        self.mqtt.publish(telemetry_topic, json.dumps(combined), retain=False)

        def pub_simple(key, topic_suffix):
            if key in combined:
                t = f"{MQTT_BASE}/{src}/{topic_suffix}"
                try:
                    val = combined[key]
                    if isinstance(val, bool):
                        valout = "1" if val else "0"
                    else:
                        valout = str(val)
                    self.mqtt.publish(t, valout, retain=False)
                except Exception as e:
                    log.debug("Failed to publish %s: %s", key, e)

        pub_simple("gate_state", "state")
        pub_simple("battery_voltage", "battery_voltage")
        pub_simple("battery_pct", "battery_pct")
        pub_simple("solar_voltage", "solar_voltage")
        pub_simple("charging", "charging")
        pub_simple("rssi", "rssi")
        pub_simple("radio_temp_c", "radio_temp_c")
        pub_simple("uptime_s", "uptime_s")
        pub_simple("limit_open", "limit_open")
        pub_simple("limit_closed", "limit_closed")
        pub_simple("photoeye_blocked", "photoeye_blocked")
        pub_simple("free_exit", "free_exit")

        if src not in self.known_nodes:
            log.info("Discovered new node %s — publishing discovery", src)
            self.publish_discovery(src)
            self.known_nodes.add(src)

    def serial_reader_loop(self):
        while True:
            try:
                if self.ser is None:
                    self.open_serial()
                line = self.ser.readline().decode('utf-8', errors='ignore')
                if line:
                    log.debug("Serial <<< %s", line.strip())
                    self.handle_incoming_line(line.strip())
            except Exception as e:
                log.error("Serial read error: %s", e)
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                time.sleep(2)

    def run(self):
        import threading
        t = threading.Thread(target=self.serial_reader_loop, daemon=True)
        t.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Shutting down")
            if self.mqtt:
                self.mqtt.loop_stop()
                self.mqtt.disconnect()
            if self.ser and self.ser.is_open:
                self.ser.close()

def parse_args():
    p = argparse.ArgumentParser(description="Apertus serial -> MQTT bridge")
    p.add_argument("--serial", default=SERIAL_PORT, help="Serial device path")
    p.add_argument("--baud", type=int, default=SERIAL_BAUD, help="Serial baud")
    p.add_argument("--mqtt-host", default=MQTT_BROKER)
    p.add_argument("--mqtt-port", type=int, default=MQTT_PORT)
    p.add_argument("--mqtt-user", default=None)
    p.add_argument("--mqtt-pass", default=None)
    return p.parse_args()

def main():
    args = parse_args()
    cfg = {"host": args.mqtt_host, "port": args.mqtt_port, "user": args.mqtt_user, "pass": args.mqtt_pass}
    bridge = SerialMqttBridge(args.serial, args.baud, cfg)
    bridge.start_mqtt()
    bridge.open_serial()
    bridge.run()

if __name__ == "__main__":
    main()