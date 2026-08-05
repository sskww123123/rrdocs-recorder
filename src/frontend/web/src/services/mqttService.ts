import mqtt from 'mqtt';

const BROKER_WS_URL = 'ws://localhost:9001';
const TOPIC_COMMANDS = 'rrdocs/reunion/comandos';
const TOPIC_STATUS   = 'rrdocs/reunion/estado';

let client: mqtt.MqttClient | null = null;

export function getMqttClient(): mqtt.MqttClient {
  if (!client || !client.connected) {
    client = mqtt.connect(BROKER_WS_URL, {
      clientId: 'rrdocs-web-' + Date.now(),
      reconnectPeriod: 2000,
    });
  }
  return client;
}

export function sendCommand(action: string, extra: Record<string, unknown> = {}) {
  const c = getMqttClient();
  const payload = JSON.stringify({ action, ...extra });
  c.publish(TOPIC_COMMANDS, payload);
}

export { TOPIC_STATUS, TOPIC_COMMANDS };
