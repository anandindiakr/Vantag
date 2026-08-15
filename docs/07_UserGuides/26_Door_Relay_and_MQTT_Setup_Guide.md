# Door Relay & MQTT Setup Guide

This guide covers the two pieces that make remote door lock/unlock work in
Vantag / Retail Nazar:

1. **Door Relay** — the physical relay board wired to your magnetic lock,
   strike, or gate controller, driven by the on-site Edge Agent.
2. **MQTT** — the secure message channel the dashboard uses to send lock/unlock
   commands to the agent and receive door status back.

---

## 1. How the pieces connect

```
Dashboard (browser)                    Vantag backend                      Store (Edge Agent)
─────────────────────                  ─────────────────                   ─────────────────────
[One-Tap Lock button] ──HTTPS──► /api/doors/... ──MQTT──► mosquitto ──MQTT──► VantagMqttClient
      ▲                                                                              │
      └────────────── door_state via authenticated WebSocket ◄───────────────────────┘
                                                                                     │
                                                                      RelayDriver (http / gpio /
                                                                      serial / modbus) actuates
                                                                      the physical relay board
```

- The **browser never talks to MQTT directly**. Door status travels over the
  authenticated backend WebSocket, so broker credentials never enter the
  frontend bundle.
- The **Edge Agent** subscribes to
  `vantag/stores/{store_id}/doors/{door_id}/command` and publishes status to
  `vantag/stores/{store_id}/doors/{door_id}/status`.

---

## 2. Door Relay setup wizard (plug-and-play)

1. Sign in to the dashboard and open **Settings → Door Relay Setup**.
2. **Step 1 — Choose a relay type** (or click **Scan network** to auto-detect):
   | Type | Typical hardware |
   |---|---|
   | WiFi / HTTP | Shelly, Tasmota, ESPHome, Sonoff, any REST relay |
   | GPIO | Raspberry Pi / single-board computer relay hat |
   | Serial / USB / RS-485 | Arduino + relay shield, USB relay boards |
   | Modbus TCP | Network Modbus relay boards |
   | Simulate | No hardware — logs commands (demo / testing) |
3. **Step 2 — Connection details** (URL, pin, serial port, or Modbus host).
4. **Step 3 — Test & save.** Press **Test unlock** to fire a command at the
   relay through the agent, then **Save configuration**.
5. Download the **driver pack** (example scripts + wiring notes for common
   boards) if you need firmware examples.

The configuration is stored per tenant and delivered to the Edge Agent
automatically on its next config poll — no agent restart required.

### Auto-discovery

The Edge Agent runs a best-effort discovery pass (mDNS + common relay HTTP
endpoints on the local gateway). Any candidates it finds appear under
**Auto-detect relays** in Step 1, so you can accept one in a single click and
only fill in credentials if the board requires them.

---

## 3. MQTT security model

The broker requires **authentication** — anonymous connections are rejected.

| Client | Credentials | Access |
|---|---|---|
| Backend (`vantag_backend`) | env `MQTT_USERNAME` / `MQTT_PASSWORD` | publish door commands, subscribe to door status |
| Edge Agent (`vantag_edge`) | env `MQTT_EDGE_USERNAME` / `MQTT_EDGE_PASSWORD` (baked into the download bundle) | subscribe to door commands, publish door status |
| Browser | *(none)* | never connects to MQTT — uses the authenticated WebSocket |

Broker passwords are stored **hashed** (`PBKDF2-SHA512`, `$7$` entries) in
`docker/mosquitto/passwd`. Plaintext credentials live only in the server-side
environment, not in the repository.

### Hardening checklist (operator)

- [ ] Set **strong, unique** `MQTT_PASSWORD` and `MQTT_EDGE_PASSWORD` in the
      production `.env` — do not leave the shipped default in place.
- [ ] Regenerate the password file after rotating:
      `mosquitto_passwd -U /path/to/docker/mosquitto/passwd`, then restart the
      broker.
- [ ] **Enable TLS on port 8883** for MQTTS. See `docker/mosquitto.conf` for
      the commented listener block, point `certfile` / `keyfile` at the VPS
      Let's Encrypt `fullchain.pem` / `privkey.pem`, open `8883`, and set
      `MQTT_AGENT_PORT=8883` so newly downloaded agents connect over MQTTS
      (the backend keeps its private-Docker connection on `1883`). The agent
      auto-enables TLS when its `mqtt_port` is `8883`.
- [ ] Restrict `1883` to the internal network only once MQTTS is live (agents
      should connect over `8883`).

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Door never moves on **Test** | No Edge Agent online at the store | Check the agent is running and shows **online** in Agent Status |
| Test returns 502 | Backend cannot reach the MQTT broker | Verify Mosquitto is healthy: `docker logs vantag-mosquitto-prod` |
| Agent logs "MQTT connect error rc=5" | Wrong broker credentials | Set `mqtt_username` / `mqtt_password` in the agent config to match the env values |
| Relay stays silent but logs "Relay (gpio→simulate)" | Optional driver dependency missing | Install `RPi.GPIO` / `pyserial` / `pymodbus` per the relay type |
| Door moves but dashboard shows "unknown" | Status topic mismatch | Ensure agent is on v1.8.0+ and `tenant_id` is set in its config |
