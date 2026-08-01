#!/usr/bin/env node

const url = process.argv[2] ?? "ws://192.168.18.51:9091";
const socket = new WebSocket(url);
const actionHistory = new Map();
let latestCandidates = [];
let latestRevision = -1;
let latestTrackingEpoch = 0;
let sawObservation = false;
let latestCandidatePayload = null;

function publish(topic, data) {
  socket.send(JSON.stringify({ op: "publish", topic, msg: { data: JSON.stringify(data) } }));
}

function action(kind, target) {
  const actionId = `BOOT-${kind}-${Date.now()}`;
  const candidate = latestCandidates.find((item) => item.id === target.id);
  if (!candidate) throw new Error(`No current grant for ${target.id}`);
  publish("/pulso/hil/action_intent", {
    contract_version: "pulso.action.v1",
    action_id: actionId,
    mission_id: "M-BOOTSTRAP-QA",
    issued_monotonic_ns: Math.trunc(performance.now() * 1_000_000),
    kind,
    target,
    candidate_capability: candidate.capability,
    expected_navigation_revision: latestRevision,
    expected_tracking_epoch: latestTrackingEpoch,
    expected_target_revision: candidate.target_revision,
    parameters: {},
  });
  return actionId;
}

function waitUntil(predicate, label, waitMs = 20_000) {
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
    }, 80);
  });
}

function finalAction(actionId) {
  return actionHistory.get(actionId)?.find((item) =>
    item.status !== "ACTIVE",
  );
}

socket.addEventListener("open", async () => {
  try {
    socket.send(JSON.stringify({
      op: "advertise",
      id: "boot-action-intent",
      topic: "/pulso/hil/action_intent",
      type: "std_msgs/msg/String",
    }));
    for (const [topic, type] of [
      ["/pulso/navigation/candidates", "std_msgs/msg/String"],
      ["/pulso/hil/action_result", "std_msgs/msg/String"],
      ["/pulso/hil/observation", "std_msgs/msg/String"],
    ]) {
      socket.send(JSON.stringify({ op: "subscribe", id: `boot-${topic}`, topic, type }));
    }
    await waitUntil(() => latestCandidates.length > 0 && sawObservation, "initial candidates and tracking");
    const completedSweeps = [];
    let frontier = latestCandidates.find((item) => item.type === "FRONTIER");
    for (let attempt = 0; !frontier && attempt < 8; attempt += 1) {
      const bootstrap = latestCandidates.find((item) => item.id.startsWith("VP_INIT_"));
      if (!bootstrap) throw new Error("No frontier or bounded bootstrap viewpoint is available");
      const beforeRevision = latestRevision;
      const lookId = action("LOOK_AT", { type: "VIEWPOINT", id: bootstrap.id });
      const result = await waitUntil(() => finalAction(lookId), `${bootstrap.id} completion`, 20_000);
      if (result.status !== "SUCCEEDED") throw new Error(`${bootstrap.id} ended as ${result.status}`);
      completedSweeps.push(bootstrap.id);
      await waitUntil(
        () => latestRevision > beforeRevision || latestCandidates.some((item) => item.type === "FRONTIER"),
        "next navigation revision",
      );
      frontier = latestCandidates.find((item) => item.type === "FRONTIER");
    }
    if (!frontier) throw new Error("SLAM did not expose a reachable frontier within eight sweeps");

    const moveAttempts = [];
    const attemptedFrontiers = new Set();
    let reachedFrontier = null;
    for (let attempt = 0; attempt < 3 && !reachedFrontier; attempt += 1) {
      frontier = latestCandidates.find((item) =>
        item.type === "FRONTIER" && !attemptedFrontiers.has(item.id),
      );
      if (!frontier) {
        throw new Error("No untried frontier remained after a physical blockage");
      }
      attemptedFrontiers.add(frontier.id);
      const beforeRevision = latestRevision;
      const moveId = action("MOVE_TO", { type: "FRONTIER", id: frontier.id });
      const moveResult = await waitUntil(
        () => finalAction(moveId),
        `frontier ${frontier.id} MOVE_TO`,
        65_000,
      );
      moveAttempts.push({
        id: frontier.id,
        status: moveResult.status,
        detail: moveResult.detail,
        statuses: actionHistory.get(moveId).map((item) => item.status),
      });
      if (moveResult.status === "SUCCEEDED") {
        reachedFrontier = frontier;
        break;
      }
      if (moveResult.status !== "BLOCKED") {
        throw new Error(`MOVE_TO ${frontier.id} ended as ${moveResult.status}`);
      }
      await waitUntil(
        () => latestRevision > beforeRevision &&
          latestCandidates.some((item) =>
            item.type === "FRONTIER" && !attemptedFrontiers.has(item.id),
          ),
        "alternate frontier after BLOCKED",
      );
    }
    if (!reachedFrontier) throw new Error("Three physical routes were BLOCKED");
    console.log(JSON.stringify({
      ok: true,
      url,
      completed_sweeps: completedSweeps,
      frontier: {
        id: reachedFrontier.id,
        path_length_m: reachedFrontier.path_length_m,
        risk: reachedFrontier.risk,
        information_gain: reachedFrontier.information_gain,
      },
      move_attempts: moveAttempts,
      final_navigation_revision: latestRevision,
    }, null, 2));
    socket.close();
  } catch (error) {
    console.error(JSON.stringify({
      ok: false,
      error: error.message,
      navigation_revision: latestRevision,
      sensor_map_seq: latestCandidatePayload?.sensor_map_seq ?? null,
      candidate_ids: latestCandidates.map((item) => item.id),
      action_history: Object.fromEntries(actionHistory),
    }, null, 2));
    socket.close();
    process.exitCode = 1;
  }
});

socket.addEventListener("message", (event) => {
  const frame = JSON.parse(event.data);
  if (frame.op !== "publish") return;
  const text = frame.msg?.data;
  if (typeof text !== "string") return;
  const payload = JSON.parse(text);
  if (frame.topic === "/pulso/navigation/candidates") {
    latestCandidatePayload = payload;
    latestCandidates = payload.candidates ?? [];
    latestRevision = payload.navigation_revision ?? latestRevision;
  } else if (frame.topic === "/pulso/hil/observation") {
    sawObservation = true;
    latestTrackingEpoch = payload.tracking?.epoch ?? latestTrackingEpoch;
  } else if (frame.topic === "/pulso/hil/action_result") {
    const history = actionHistory.get(payload.action_id) ?? [];
    history.push(payload);
    actionHistory.set(payload.action_id, history);
  }
});

socket.addEventListener("error", () => {
  process.exitCode = 1;
});
