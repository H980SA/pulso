import { parseRosbridgeFrame, SUBSCRIPTIONS } from "./contracts.js";

export class RosbridgeClient {
  constructor(url, listeners = {}) {
    this.url = url;
    this.listeners = listeners;
    this.socket = null;
    this.retryTimer = null;
    this.retryCount = 0;
    this.closedByOperator = false;
  }

  connect() {
    if (this.socket && this.socket.readyState < WebSocket.CLOSING) return;
    this.closedByOperator = false;
    this.listeners.onStatus?.("connecting", `Conectando a ${this.url}`);
    let socket;
    try {
      socket = new WebSocket(this.url);
    } catch (error) {
      this.fail(error);
      return;
    }
    this.socket = socket;
    socket.addEventListener("open", () => this.open(socket));
    socket.addEventListener("message", (event) => this.message(event.data));
    socket.addEventListener("error", () => this.listeners.onStatus?.("error", "Error de WebSocket"));
    socket.addEventListener("close", (event) => this.closeEvent(event));
  }

  disconnect() {
    this.closedByOperator = true;
    clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.socket?.close(1000, "Mission control disconnected");
    this.socket = null;
    this.listeners.onStatus?.("waiting", "Desconectado por el operador");
  }

  publishOperatorCommand(command) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("El enlace ROS con el S25 no está conectado");
    }
    const payload = {
      command,
      nonce: crypto.randomUUID(),
      issued_at_ms: Date.now(),
    };
    this.socket.send(JSON.stringify({
      op: "publish",
      topic: "/pulso/operator/command",
      msg: { data: JSON.stringify(payload) },
    }));
    return payload.nonce;
  }

  open(socket) {
    if (socket !== this.socket) return;
    this.retryCount = 0;
    for (const [topic, type, throttleRate] of SUBSCRIPTIONS) {
      const request = {
        op: "subscribe",
        id: `mission-control:${topic}`,
        topic,
        throttle_rate: throttleRate,
        queue_length: 1,
      };
      if (type) request.type = type;
      socket.send(JSON.stringify(request));
    }
    this.listeners.onStatus?.("live", `Suscrito a ${SUBSCRIPTIONS.length} tópicos`);
  }

  message(rawFrame) {
    const event = parseRosbridgeFrame(rawFrame);
    if (!event) return;
    if (event.kind === "bridge-status") {
      this.listeners.onBridgeMessage?.(event);
      return;
    }
    this.listeners.onEvent?.(event, { topic: frameTopic(rawFrame) });
  }

  closeEvent(event) {
    if (event.target !== this.socket) return;
    this.socket = null;
    if (this.closedByOperator) return;
    const delayMs = Math.min(10_000, 750 * 2 ** this.retryCount);
    this.retryCount += 1;
    this.listeners.onStatus?.("waiting", `Reconexión en ${(delayMs / 1000).toFixed(1)}s`);
    this.retryTimer = setTimeout(() => this.connect(), delayMs);
  }

  fail(error) {
    this.listeners.onStatus?.("error", error?.message || "No se pudo abrir WebSocket");
  }
}

function frameTopic(rawFrame) {
  if (typeof rawFrame !== "string") return rawFrame?.topic || "unknown";
  try {
    const value = JSON.parse(rawFrame);
    return typeof value?.topic === "string" ? value.topic : "unknown";
  } catch {
    return "unknown";
  }
}

export function resolveBridgeUrl(locationLike = window.location) {
  const params = new URLSearchParams(locationLike.search || "");
  const configured = params.get("bridge");
  if (configured) return configured;
  const protocol = locationLike.protocol === "https:" ? "wss:" : "ws:";
  const hostname = locationLike.hostname || "127.0.0.1";
  return `${protocol}//${hostname}:9091`;
}
