#!/usr/bin/env python3
"""
apertus-detect-serial.py

Detect Apertus Gateway serial device by scanning /dev/ttyUSB* and /dev/ttyACM*.
When the gateway JSON ready marker is detected ({"gateway":"apertus_ready"}),
write /etc/apertus/apertus.env with APERTUS_SERIAL and preserve other fields.

Run as root (it writes /etc/apertus/apertus.env).
"""

import glob
import json
import os
import serial
import time

ENV_PATH = "/etc/apertus/apertus.env"
CANDIDATES = []
CANDIDATES.extend(glob.glob("/dev/ttyUSB*"))
CANDIDATES.extend(glob.glob("/dev/ttyACM*"))
CANDIDATES.extend(glob.glob("/dev/serial/by-id/*"))

OPEN_TIMEOUT = 2.0
READ_TIMEOUT = 0.5
PROBE_DURATION = 3.0  # seconds to listen to each device

def read_env_template():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def write_env(env):
    os.makedirs(os.path.dirname(ENV_PATH), exist_ok=True)
    with open(ENV_PATH + ".tmp", "w") as f:
        for k, v in env.items():
            # Quote values with spaces or empty values explicitly
            if v is None:
                v = ""
            if " " in str(v) or v == "":
                f.write(f'{k}="{v}"\n')
            else:
                f.write(f'{k}={v}\n')
    os.replace(ENV_PATH + ".tmp", ENV_PATH)
    os.chmod(ENV_PATH, 0o640)

def probe_device(path):
    try:
        real = os.path.realpath(path)
        port = real if os.path.exists(real) else path
        ser = serial.Serial(port, baudrate=115200, timeout=READ_TIMEOUT, write_timeout=1, exclusive=True)
    except Exception:
        return False, None
    try:
        start = time.time()
        while time.time() - start < PROBE_DURATION:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
            except Exception:
                line = None
            if not line:
                continue
            # look for the ready marker that Gateway emits: {"gateway":"apertus_ready"}
            if '"gateway"' in line and 'apertus_ready' in line:
                ser.close()
                return True, port
            # occasionally the gateway prints JSON lines for incoming radio packets too
            # so presence of "src" + "payload" may also indicate it's our device
            if line.startswith("{") and ("\"src\"" in line and "\"payload\"" in line):
                try:
                    j = json.loads(line)
                    # heuristic: payload often includes "battery_voltage" or "gate_state"
                    p = j.get("payload")
                    if p and ("battery_voltage" in str(p) or "gate_state" in str(p)):
                        ser.close()
                        return True, port
                except Exception:
                    pass
        ser.close()
    except Exception:
        try:
            ser.close()
        except Exception:
            pass
    return False, None

def main():
    print("Apertus detect: scanning serial devices...")
    env = read_env_template()
    # If APERTUS_SERIAL already exists and is present, keep it
    current = env.get("APERTUS_SERIAL")
    if current and os.path.exists(current):
        print(f"Existing APERTUS_SERIAL {current} exists; leaving unchanged.")
        return 0

    for candidate in CANDIDATES:
        found, port = probe_device(candidate)
        if found:
            print(f"Found Apertus gateway on {port}")
            env["APERTUS_SERIAL"] = port
            # set defaults if missing
            env.setdefault("APERTUS_BAUD", "115200")
            env.setdefault("APERTUS_MQTT_HOST", "localhost")
            env.setdefault("APERTUS_MQTT_PORT", "1883")
            write_env(env)
            print(f"Wrote {ENV_PATH} with APERTUS_SERIAL={port}")
            return 0

    # If we reach here, nothing found. Do not overwrite existing env unless it exists
    print("Apertus gateway not found on candidate devices. No changes made.")
    # Ensure env file exists so service has something to read; write defaults if missing
    if not os.path.exists(ENV_PATH):
        env.setdefault("APERTUS_SERIAL", "/dev/ttyUSB0")
        env.setdefault("APERTUS_BAUD", "115200")
        env.setdefault("APERTUS_MQTT_HOST", "localhost")
        env.setdefault("APERTUS_MQTT_PORT", "1883")
        write_env(env)
        print(f"Wrote default {ENV_PATH}; edit as needed if the gateway uses a different device.")
    return 1

if __name__ == "__main__":
    exit(main())