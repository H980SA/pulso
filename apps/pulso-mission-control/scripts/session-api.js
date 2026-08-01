const JSON_HEADERS = Object.freeze({ "Content-Type": "application/json" });

export class SessionRecorder {
  constructor({ missionId = "M-001", onStatus = () => {} } = {}) {
    this.missionId = missionId;
    this.onStatus = onStatus;
    this.session = null;
    this.queue = Promise.resolve();
    this.closed = false;
  }

  record(event, topic, receivedAt) {
    if (this.closed) return Promise.resolve(null);
    this.queue = this.queue
      .then(() => this.ensureSession(event))
      .then((session) => appendEvent(session.session_id, event, topic, receivedAt))
      .then((receipt) => {
        this.onStatus("saved", { ...this.session, event_count: receipt.seq, integrity_hash: receipt.event_hash });
        return receipt;
      })
      .catch((error) => {
        this.onStatus("error", this.session, error);
        return null;
      });
    return this.queue;
  }

  async ensureSession(event) {
    if (this.session) return this.session;
    const source = event.kind === "observation" ? event.source : "ROS_LIVE";
    this.onStatus("saving", null);
    this.session = await requestJson("/api/sessions", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ mission_id: this.missionId, source, mode: "LIVE" }),
    });
    this.onStatus("saved", this.session);
    return this.session;
  }

  async close() {
    this.closed = true;
    await this.queue;
    if (!this.session) return null;
    this.session = await requestJson(`/api/sessions/${this.session.session_id}/close`, {
      method: "POST", headers: JSON_HEADERS, body: "{}",
    });
    this.onStatus("saved", this.session);
    return this.session;
  }
}

export async function listSessions() {
  const value = await requestJson("/api/sessions?limit=100");
  return Array.isArray(value.sessions) ? value.sessions : [];
}

export async function readSession(sessionId) {
  const session = await requestJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
  if (session.integrity_valid !== true) {
    throw new Error(`Integridad inválida: ${session.integrity_detail || "la cadena no pudo verificarse"}`);
  }
  return session;
}

export function exportUrl(sessionId) {
  return `/api/sessions/${encodeURIComponent(sessionId)}/export`;
}

export async function replaySession(session, ingest, { onProgress = () => {} } = {}) {
  const events = Array.isArray(session.events) ? session.events : [];
  if (!events.length) return;
  const firstAt = events[0].received_at_ms;
  let previousOffset = 0;
  for (const row of events) {
    const offset = Math.max(0, row.received_at_ms - firstAt);
    const delay = Math.min(220, Math.max(0, offset - previousOffset));
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    const event = await hydrateArtifact(row.event, row.artifact_sha256);
    ingest(event, offset, {
      seq: row.seq,
      topic: row.topic,
      artifactSha256: row.artifact_sha256,
      eventHash: row.event_hash,
    });
    previousOffset = offset;
    onProgress(row.seq, events.length);
  }
}

async function appendEvent(sessionId, event, topic, receivedAt) {
  const persisted = { ...event };
  let artifact = null;
  if (typeof persisted.base64 === "string") {
    artifact = {
      base64: persisted.base64,
      content_type: `image/${String(persisted.format).toLowerCase().includes("png") ? "png" : "jpeg"}`,
    };
    delete persisted.base64;
  }
  return requestJson(`/api/sessions/${encodeURIComponent(sessionId)}/events`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      topic: topic || "unknown", received_at_ms: receivedAt, event: persisted, artifact,
    }),
  });
}

async function hydrateArtifact(event, digest) {
  if (!digest) return event;
  const response = await fetch(`/api/artifacts/${digest}`);
  if (!response.ok) throw new Error(`Artifact ${digest.slice(0, 10)} unavailable`);
  const buffer = new Uint8Array(await response.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < buffer.length; offset += 0x8000) {
    binary += String.fromCharCode(...buffer.subarray(offset, offset + 0x8000));
  }
  const format = response.headers.get("Content-Type")?.includes("png") ? "png" : "jpeg";
  return { ...event, base64: btoa(binary), format };
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  let value;
  try {
    value = await response.json();
  } catch {
    value = {};
  }
  if (!response.ok) throw new Error(value.error || `${response.status} ${response.statusText}`);
  return value;
}
