
```c name=Apertus_Gate.ino
/*
  Apertus_Gate.ino — Gate node (Arduino Nano) for Apertus
  - 5V Arduino Nano + Adafruit RFM69HCW breakout (breakout handles level shifting)
  - Telemetry: battery_voltage, solar_voltage, battery_pct, charging, rssi, radio_temp_c, uptime_s
  - Monitors Patriot board signals: limit switches, photoeye, free-exit
  - Supports commands: OPEN, CLOSE, STOP, LATCH, UNLATCH, TIMER_CLOSE
  - TODO: debounce inputs, verify J8 pin mapping before wiring, calibrate ADC, add deep-sleep
*/

#include <SPI.h>
#include <RFM69.h>

// ===== Configuration =====
#define RF69_FREQ 915.0

// RFM69 pins (Arduino Nano)
const uint8_t PIN_RFM_CS    = 10; // SS
const uint8_t PIN_RFM_INT   = 2;  // D2 external interrupt (DIO0)
const uint8_t PIN_RFM_RST   = 9;  // optional reset

// Actuators (momentary dry-contact emulation)
const uint8_t PIN_ACT_OPEN   = 3;
const uint8_t PIN_ACT_CLOSE  = 4;
const uint8_t PIN_ACT_STOP   = 5;
const uint8_t PIN_ACT_LATCH  = 11; // optional
const uint8_t PIN_ACT_UNLATCH= 12; // optional
const uint8_t PIN_ACT_TIMER  = 13; // optional

// Board status inputs (wire to Patriot J8 outputs / sensor lines)
const uint8_t PIN_LIMIT_OPEN   = 6; // active LOW with INPUT_PULLUP assumed
const uint8_t PIN_LIMIT_CLOSED = 7;
const uint8_t PIN_PHOTOEYE     = 8;
const uint8_t PIN_FREE_EXIT    = A2; // mapped as digital (use digitalRead)

// ADC Telemetry
const uint8_t PIN_BATT_ADC  = A0;
const uint8_t PIN_SOLAR_ADC = A1; // optional

// RFM69 object (isHighPower = true for HCW)
RFM69 rf69(PIN_RFM_CS, PIN_RFM_INT, true);

// Radio IDs
const uint8_t RF_GATEWAY_ID = 10;
const uint8_t RF_NODE_ID    = 20;
const uint8_t RF_NETWORK_ID = 100;

// AES key (16 bytes) - REPLACE with secure key before production
const char RF_AES_KEY[16] = "0123456789abcdef";

// Telemetry / timing
unsigned long lastTelemetryMs = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 60UL * 1000UL; // 60s

// Calibration: divider factor for ADC -> battery voltage
const float BATTERY_DIVIDER_FACTOR = 4.03f; // example for 100k/33k
const float SOLAR_DIVIDER_FACTOR   = 4.03f;

// Battery percent linear mapping (lead-acid)
const float BATTERY_VOLTS_MIN = 11.5f;
const float BATTERY_VOLTS_MAX = 13.6f;

// ===== Helpers =====
float readADCVoltage(uint8_t pin, float dividerFactor) {
  int raw = analogRead(pin);
  float vref = 5.0f; // 5V Nano ADC reference
  float vout = (raw / 1023.0f) * vref;
  return vout * dividerFactor;
}
float readBatteryVoltage() { return readADCVoltage(PIN_BATT_ADC, BATTERY_DIVIDER_FACTOR); }
float readSolarVoltage()   { return readADCVoltage(PIN_SOLAR_ADC, SOLAR_DIVIDER_FACTOR); }
int readRadioRSSI()       { return rf69.readRSSI(true); }
int readRadioTempC()      { return rf69.readTemperature(0); } // library-dependent
uint32_t getUptimeSeconds(){ return (uint32_t)(millis() / 1000UL); }
bool readActiveLow(uint8_t pin){ return digitalRead(pin) == LOW; }

void pulsePin(uint8_t pin, uint16_t ms = 200) {
  digitalWrite(pin, HIGH);
  delay(ms);
  digitalWrite(pin, LOW);
}

void applyActuatorCommand(const char* cmd) {
  if (strcmp(cmd, "OPEN") == 0) pulsePin(PIN_ACT_OPEN, 200);
  else if (strcmp(cmd, "CLOSE") == 0) pulsePin(PIN_ACT_CLOSE, 200);
  else if (strcmp(cmd, "STOP") == 0) pulsePin(PIN_ACT_STOP, 200);
  else if (strcmp(cmd, "LATCH") == 0) pulsePin(PIN_ACT_LATCH, 200);
  else if (strcmp(cmd, "UNLATCH") == 0) pulsePin(PIN_ACT_UNLATCH, 200);
  else if (strcmp(cmd, "TIMER_CLOSE") == 0) pulsePin(PIN_ACT_TIMER, 200);
}

int batteryPctFromVoltage(float v) {
  if (v <= BATTERY_VOLTS_MIN) return 0;
  if (v >= BATTERY_VOLTS_MAX) return 100;
  float pct = (v - BATTERY_VOLTS_MIN) / (BATTERY_VOLTS_MAX - BATTERY_VOLTS_MIN);
  return (int)(pct * 100.0f + 0.5f);
}

void sendTelemetryToGateway() {
  float vbatt = readBatteryVoltage();
  float vsolar = readSolarVoltage();
  bool charging = (vsolar > (vbatt + 0.2f)); // heuristic
  int rssi = readRadioRSSI();
  int radio_temp = readRadioTempC();
  uint32_t uptime_s = getUptimeSeconds();

  bool limitOpen = readActiveLow(PIN_LIMIT_OPEN);
  bool limitClosed = readActiveLow(PIN_LIMIT_CLOSED);
  bool photoeyeBlocked = readActiveLow(PIN_PHOTOEYE);
  bool freeExit = readActiveLow(PIN_FREE_EXIT);

  const char* gate_state = "unknown";
  if (limitOpen && !limitClosed) gate_state = "open";
  else if (limitClosed && !limitOpen) gate_state = "closed";
  else if (!limitOpen && !limitClosed) gate_state = "moving";

  char payload[512];
  int n = snprintf(payload, sizeof(payload),
    "{\"src\":%u,\"gate_state\":\"%s\",\"limit_open\":%d,\"limit_closed\":%d,"
    "\"photoeye_blocked\":%d,\"free_exit\":%d,\"battery_voltage\":%.2f,"
    "\"battery_pct\":%d,\"solar_voltage\":%.2f,\"charging\":%d,"
    "\"rssi\":%d,\"radio_temp_c\":%d,\"uptime_s\":%lu}",
    RF_NODE_ID,
    gate_state,
    limitOpen, limitClosed,
    photoeyeBlocked, freeExit,
    vbatt, batteryPctFromVoltage(vbatt), vsolar, charging ? 1 : 0,
    rssi, radio_temp, uptime_s
  );

  rf69.sendWithRetry(RF_GATEWAY_ID, (uint8_t*)payload, n);
}

// ===== Setup & Loop =====
void setup() {
  pinMode(PIN_ACT_OPEN, OUTPUT);  digitalWrite(PIN_ACT_OPEN, LOW);
  pinMode(PIN_ACT_CLOSE, OUTPUT); digitalWrite(PIN_ACT_CLOSE, LOW);
  pinMode(PIN_ACT_STOP, OUTPUT);  digitalWrite(PIN_ACT_STOP, LOW);
  pinMode(PIN_ACT_LATCH, OUTPUT); digitalWrite(PIN_ACT_LATCH, LOW);
  pinMode(PIN_ACT_UNLATCH, OUTPUT); digitalWrite(PIN_ACT_UNLATCH, LOW);
  pinMode(PIN_ACT_TIMER, OUTPUT);  digitalWrite(PIN_ACT_TIMER, LOW);

  pinMode(PIN_LIMIT_OPEN, INPUT_PULLUP);
  pinMode(PIN_LIMIT_CLOSED, INPUT_PULLUP);
  pinMode(PIN_PHOTOEYE, INPUT_PULLUP);
  pinMode(PIN_FREE_EXIT, INPUT_PULLUP);

  analogReference(DEFAULT);

  Serial.begin(115200);
  delay(200);

  SPI.begin();
  if (!rf69.initialize(RF69_FREQ, RF_NODE_ID, RF_NETWORK_ID)) {
    Serial.println(F("RFM69 init failed"));
  } else {
    rf69.setHighPower();
    rf69.encrypt((uint8_t*)RF_AES_KEY);
    rf69.enableAutoPower(true);
    Serial.println(F("RFM69 initialized (Apertus Gate)"));
  }

  lastTelemetryMs = millis();
  sendTelemetryToGateway(); // initial boot telemetry
}

void loop() {
  if (rf69.receiveDone()) {
    char cmd[128] = {0};
    int copyLen = min((int)rf69.DATALEN, (int)sizeof(cmd)-1);
    memcpy(cmd, (char*)rf69.DATA, copyLen);
    cmd[copyLen] = '\0';
    Serial.print(F("Radio recv from "));
    Serial.print(rf69.SENDERID);
    Serial.print(F(": "));
    Serial.println(cmd);

    applyActuatorCommand(cmd);

    const char* ack = "ACK";
    rf69.sendWithRetry(RF_GATEWAY_ID, (uint8_t*)ack, strlen(ack));
    delay(50);
    sendTelemetryToGateway();
  }

  if (millis() - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    sendTelemetryToGateway();
    lastTelemetryMs = millis();
  }

  // TODO: add rf69.sleep() and MCU low-power for battery life
  delay(100);
}
