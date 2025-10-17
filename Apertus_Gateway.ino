/* Apertus_Gateway.ino — Gateway node (Arduino Nano) for Apertus
   - Acts as an RFM69 <-> USB-Serial bridge. Connect this Nano to Home Assistant host via USB.
   - Serial protocol: TO:<dest_id>:<payload>\n to send radio commands.
   - Radio-received messages printed as JSON lines (for bridge to publish to MQTT).
   - TODO: secure serial channel if host is untrusted.
*/

#include <SPI.h>
#include <RFM69.h>

#define RF69_FREQ 915.0

const uint8_t PIN_RFM_CS    = 10;
const uint8_t PIN_RFM_INT   = 2;
const uint8_t PIN_RFM_RST   = 9;

RFM69 rf69(PIN_RFM_CS, PIN_RFM_INT, true);

const uint8_t RF_GATEWAY_ID = 10;
const uint8_t RF_NETWORK_ID = 100;

// AES key must match nodes
const char RF_AES_KEY[16] = "0123456789abcdef";

#define SERIAL_BUF_LEN 512
char serialBuf[SERIAL_BUF_LEN];
uint16_t serialPos = 0;

void setup() {
  Serial.begin(115200);
  delay(200);
  SPI.begin();
  if (!rf69.initialize(RF69_FREQ, RF_GATEWAY_ID, RF_NETWORK_ID)) {
    Serial.println(F("RFM69 init failed"));
  } else {
    rf69.setHighPower();
    rf69.encrypt((uint8_t*)RF_AES_KEY);
    rf69.enableAutoPower(true);
    Serial.println(F("Apertus Gateway RFM69 initialized"));
  }
  Serial.println(F("{\"gateway\":\"apertus_ready\"}"));
}

void forwardSerialToRadio(const char* line) {
  if (strncmp(line, "TO:", 3) != 0) {
    Serial.print(F("{\"err\":\"unknown_serial_cmd\",\"line\":\""));
    Serial.print(line);
    Serial.println(F("\"}"));
    return;
  }
  const char* p = line + 3;
  int dest = atoi(p);
  const char* colon = strchr(p, ':');
  if (!colon) {
    Serial.println(F("{\"err\":\"bad_format\"}"));
    return;
  }
  const char* payload = colon + 1;
  size_t len = strlen(payload);
  while (len > 0 && (payload[len-1] == '\n' || payload[len-1] == '\r')) { len--; }
  if (len == 0) {
    Serial.println(F("{\"err\":\"empty_payload\"}"));
    return;
  }
  uint8_t sendBuf[192];
  if (len > sizeof(sendBuf)-1) len = sizeof(sendBuf)-1;
  memcpy(sendBuf, payload, len);
  sendBuf[len] = 0;

  bool ok = rf69.sendWithRetry((uint8_t)dest, sendBuf, len);
  if (ok) {
    Serial.print(F("{\"sent_to\":"));
    Serial.print(dest);
    Serial.print(F(",\"payload\":\""));
    Serial.print(payload);
    Serial.println(F("\"}"));
  } else {
    Serial.print(F("{\"sent_error_to\":"));
    Serial.print(dest);
    Serial.println(F("}"));
  }
}

void loop() {
  if (rf69.receiveDone()) {
    int src = rf69.SENDERID;
    int rssi = rf69.readRSSI(true);
    char payload[RH_RF69_MAX_MESSAGE_LEN + 1];
    int n = min((int)rf69.DATALEN, RH_RF69_MAX_MESSAGE_LEN);
    memcpy(payload, rf69.DATA, n);
    payload[n] = '\0';

    // Emit JSON line for bridge
    Serial.print("{\"src\":");
    Serial.print(src);
    Serial.print(",\"rssi\":");
    Serial.print(rssi);
    Serial.print(",\"payload\":\"");
    for (int i = 0; i < n; ++i) {
      char c = payload[i];
      if (c == '"' || c == '\\') Serial.print('\\');
      Serial.print(c);
    }
    Serial.println("\"}");
  }

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      serialBuf[serialPos] = 0;
      if (serialPos > 0) forwardSerialToRadio(serialBuf);
      serialPos = 0;
    } else {
      if (serialPos < SERIAL_BUF_LEN - 1) serialBuf[serialPos++] = c;
      else serialPos = 0;
    }
  }
  delay(10);
}