#!/usr/bin/env node

const url = process.argv[2] ?? "ws://192.168.18.51:9091";
const socket = new WebSocket(url);
const history = new Map();
let candidates = [];
let navigationRevision = -1;
let trackingEpoch = 0;
let motionState = "UNKNOWN";

function publish(data) {
  socket.send(JSON.stringify({
    op: "publish",
    topic: "/pulso/hil/action_intent",
    msg: { data: JSON.stringify(data) },
  }));
}

function waitUntil(predicate, label, waitMs = 10_000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      const value = predicate();
      if (value) {
        clearInterval(timer);
        resolve(value);
      } else if (Date.now() - started > waitMs) {
        clearInterval(timer);
        reject(new Error(`Timed out waiting for ${label}`));
      }
    }, 50);
  });
}

socket.addEventListener("open", async () => {
  try {
    socket.send(JSON.stringify({
      op: "advertise",
      id: "stop-action-intent",
      topic: "/pulso/hil/action_intent",
      type: "std_msgs/msg/String",
    }));
    for (const [topic, type] of [
      ["/pulso/navigation/candidates", "std_msgs/msg/String"],
      ["/pulso/hil/action_result", "std_msgs/msg/String"],
      ["/pulso/hil/observation", "std_msgs/msg/String"],
    ]) {
      socket.send(JSON.stringify({ op: "subscribe", topic, type }));
    }
    await waitUntil(
      () => candidates.some((item) => item.type === "FRONTIER" || item.id.endsWith("_3")) && trackingEpoch > 0,
      "interruptible navigation grant",
    );
    const candidate = candidates
      .filter((item) => item.type === "FRONTIER")
      .sort((a, b) => (b.path_length_m ?? 0) - (a.path_length_m ?? 0))[0]
      ?? candidates.find((item) => item.id.endsWith("_3"));
    const motionKind = candidate.type === "FRONTIER" ? "MOVE_TO" : "LOOK_AT";
    const motionId = `STOP-QA-MOTION-${Date.now()}`;
    publish({
      contract_version: "pulso.action.v1",
      action_id: motionId,
      mission_id: "M-STOP-QA",
      issued_monotonic_ns: Math.trunc(performance.now() * 1_000_000),
      kind: motionKind,
      target: { type: candidate.type, id: candidate.id },
      candidate_capability: candidate.capability,
      expected_navigation_revision: navigationRevision,
      expected_tracking_epoch: trackingEpoch,
      expected_target_revision: candidate.target_revision,
      parameters: {},
    });
    await waitUntil(() => history.get(motionId)?.some((item) => item.status === "ACTIVE"), "ACTIVE");
    const stopId = `STOP-QA-${Date.now()}`;
    publish({
      contract_version: "pulso.action.v1",
      action_id: stopId,
      mission_id: "M-STOP-QA",
      issued_monotonic_ns: Math.trunc(performance.now() * 1_000_000),
      kind: "STOP",
      target: null,
      parameters: { reason: "operator_test" },
    });
    await waitUntil(
      () => history.get(motionId)?.some((item) => item.status === "CANCELLED"),
      "cancelled motion",
    );
    await waitUntil(
      () => history.get(stopId)?.some((item) => item.status === "SUCCEEDED"),
      "STOP success",
    );
    await waitUntil(() => motionState === "STOPPED", "stopped observation");
    console.log(JSON.stringify({
      ok: true,
      motion_kind: motionKind,
      candidate_id: candidate.id,
      motion_statuses: history.get(motionId).map((item) => item.status),
      stop_statuses: history.get(stopId).map((item) => item.status),
      final_motion_state: motionState,
    }, null, 2));
    socket.close();
  } catch (error) {
    console.error(JSON.stringify({ ok: false, error: error.message }));
    socket.close();
    process.exitCode = 1;
  }
});

socket.addEventListener("message", (event) => {
  const frame = JSON.parse(event.data);
  if (frame.op !== "publish" || typeof frame.msg?.data !== "string") return;
  const payload = JSON.parse(frame.msg.data);
  if (frame.topic === "/pulso/navigation/candidates") {
    candidates = payload.candidates ?? [];
    navigationRevision = payload.navigation_revision ?? navigationRevision;
  } else if (frame.topic === "/pulso/hil/observation") {
    trackingEpoch = payload.tracking?.epoch ?? trackingEpoch;
    motionState = payload.robot?.motion_state ?? motionState;
  } else if (frame.topic === "/pulso/hil/action_result") {
    const items = history.get(payload.action_id) ?? [];
    items.push(payload);
    history.set(payload.action_id, items);
  }
});

socket.addEventListener("error", () => { process.exitCode = 1; });
