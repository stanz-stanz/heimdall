/** WebSocket client with auto-reconnect using Svelte 5 runes. */

export const wsState = $state({ connected: false, lastMessage: null, messages: [] });

let ws = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let pingInterval = null;

const MAX_RECONNECT_DELAY = 30_000;
const MAX_MESSAGES = 500;

function getBackoff() {
  const base = Math.min(1000 * 2 ** reconnectAttempts, MAX_RECONNECT_DELAY);
  const jitter = Math.random() * base * 0.3;
  return base + jitter;
}

export function connect() {
  if (ws?.readyState === WebSocket.OPEN) return;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/console/ws`;

  ws = new WebSocket(url);

  ws.onopen = () => {
    wsState.connected = true;
    reconnectAttempts = 0;

    pingInterval = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30_000);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'pong') return;
      wsState.lastMessage = msg;
      wsState.messages = [...wsState.messages.slice(-(MAX_MESSAGES - 1)), msg];
    } catch {
      console.warn('Non-JSON WebSocket message:', event.data);
    }
  };

  ws.onclose = () => {
    cleanup();
    wsState.connected = false;
    scheduleReconnect();
  };

  ws.onerror = () => {
    cleanup();
    wsState.connected = false;
  };
}

function cleanup() {
  if (pingInterval) clearInterval(pingInterval);
  pingInterval = null;
}

function scheduleReconnect() {
  const delay = getBackoff();
  reconnectAttempts++;
  reconnectTimer = setTimeout(connect, delay);
}

export function disconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  cleanup();
  ws?.close();
  ws = null;
  wsState.connected = false;
}

export function send(type, payload = {}) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type, payload, ts: Date.now() / 1000 }));
  } else {
    console.warn('WebSocket not open — message dropped:', type);
  }
}
