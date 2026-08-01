#!/usr/bin/env node

const url = process.argv[2] ?? "ws://192.168.18.51:9091";
const timeoutMs = 35_000;
const socket = new WebSocket(url);
const actionHistory = new Map();
let latestCandidates = [];
let sawObservation = false;
let sawRgb = false;
let sawCandidates = false;
let latestNavigationRevision = 0;
let latestTrackingEpoch = 0;
let latestRgbCaptureNs = 0;
let perceptionTimer;

function publish(topic, data) {
  socket.send(JSON.stringify({ op: "publish", topic, msg: { data: JSON.stringify(data) } }));
}

function action(kind, target = null, parameters = {}) {
  const actionId = `QA-${kind}-${Date.now()}`;
  const payload = {
    contract_version: "pulso.action.v1",
    action_id: actionId,
    mission_id: "M-QA",
    issued_monotonic_ns: Math.trunc(performance.now() * 1_000_000),
    kind,
    target,
    parameters,
  };
  if (target) {
    const candidate = latestCandidates.find((item) => item.id === target.id);
    if (!candidate) throw new Error(`No current grant for ${target.id}`);
    payload.candidate_capability = candidate.capability;
    payload.expected_navigation_revision = latestNavigationRevision;
    payload.expected_tracking_epoch = latestTrackingEpoch;
    payload.expected_target_revision = candidate.target_revision;
  }
  publish("/pulso/hil/action_intent", payload);
  return actionId;
}

function waitUntil(predicate, label, waitMs = 12_000) {
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

function publishQaTrack() {
  publish("/pulso/hil/perception_tracks", {
    contract_version: "pulso.perception.tracks.v1",
    captured_monotonic_ns: Math.trunc(performance.now() * 1_000_000),
    frame_id: "phone_camera_optical_frame",
    tracks: [{
      id: "QA_PERSON_1",
      label: "person",
      confidence: 0.82,
      bearing_deg: 22.0,
      box_norm: [0.55, 0.2, 0.78, 0.92],
      revision: 1,
    }],
  });
}

const deadline = setTimeout(() => {
  console.error(JSON.stringify({ ok: false, error: "global timeout" }));
  socket.close();
  process.exitCode = 1;
}, timeoutMs);

socket.addEventListener("open", async () => {
  try {
    const topics = [
      ["/pulso/hil/observation", "std_msgs/msg/String"],
      ["/pulso/navigation/candidates", "std_msgs/msg/String"],
      ["/pulso/hil/action_result", "std_msgs/msg/String"],
      ["/pulso/phone/rgb/compressed", "sensor_msgs/msg/CompressedImage"],
    ];
    for (const [topic, type] of topics) {
      socket.send(JSON.stringify({
        op: "subscribe",
        id: `qa-${topic}`,
        topic,
        type,
        throttle_rate: topic.endsWith("compressed") ? 900 : 0,
        queue_length: 1,
      }));
    }
    await waitUntil(() => sawObservation && sawRgb && sawCandidates, "live HIL streams");

    const bootstrap = latestCandidates.find((item) => item.id.startsWith("VP_INIT_"));
    if (bootstrap) {
      const surveyId = action("LOOK_AT", { type: "VIEWPOINT", id: bootstrap.id });
      await waitUntil(() => finalAction(surveyId), "bootstrap LOOK_AT", 18_000);
    }

    publishQaTrack();
    perceptionTimer = setInterval(publishQaTrack, 800);
    await waitUntil(
      () => latestCandidates.find((item) => item.id === "QA_PERSON_1" && item.type === "TARGET"),
      "TARGET candidate",
    );

    const lookId = action("LOOK_AT", { type: "TARGET", id: "QA_PERSON_1" });
    await waitUntil(() => finalAction(lookId), "target LOOK_AT");

    const rgbBeforeRequest = latestRgbCaptureNs;
    const viewId = action(
      "REQUEST_VIEW",
      { type: "TARGET", id: "QA_PERSON_1" },
      { view_kind: "TARGET_VIEW" },
    );
    const viewResult = await waitUntil(() => finalAction(viewId), "TARGET_VIEW");
    await waitUntil(() => latestRgbCaptureNs > rgbBeforeRequest, "post-request RGB capture");

    const lightOnId = action("SET_FLASHLIGHT", null, { enabled: true });
    await waitUntil(() => finalAction(lightOnId), "flashlight on");
    const lightOffId = action("SET_FLASHLIGHT", null, { enabled: false });
    await waitUntil(() => finalAction(lightOffId), "flashlight off");

    console.log(JSON.stringify({
      ok: true,
      url,
      observation: sawObservation,
      rgb: sawRgb,
      candidate_types: [...new Set(latestCandidates.map((item) => item.type))],
      target_view_topic: viewResult.data?.artifact_topic,
      fresh_rgb_after_request: latestRgbCaptureNs > rgbBeforeRequest,
      actions: Object.fromEntries(
        [...actionHistory].map(([id, history]) => [id, history.map((item) => item.status)]),
      ),
    }, null, 2));
    clearTimeout(deadline);
    clearInterval(perceptionTimer);
    socket.close();
  } catch (error) {
    clearTimeout(deadline);
    clearInterval(perceptionTimer);
    console.error(JSON.stringify({ ok: false, error: error.message }));
    socket.close();
    process.exitCode = 1;
  }
});

socket.addEventListener("message", (event) => {
  const frame = JSON.parse(event.data);
  if (frame.op !== "publish") return;
  if (frame.topic === "/pulso/phone/rgb/compressed") {
    sawRgb = Boolean(frame.msg?.data);
    const stamp = frame.msg?.header?.stamp;
    if (stamp) latestRgbCaptureNs = Number(stamp.sec) * 1e9 + Number(stamp.nanosec);
    return;
  }
  const text = frame.msg?.data;
  if (typeof text !== "string") return;
  const payload = JSON.parse(text);
  if (frame.topic === "/pulso/hil/observation") {
    sawObservation = true;
    latestTrackingEpoch = payload.tracking?.epoch ?? latestTrackingEpoch;
  }
  if (frame.topic === "/pulso/navigation/candidates") {
    sawCandidates = true;
    latestCandidates = payload.candidates ?? [];
    latestNavigationRevision = payload.navigation_revision ?? latestNavigationRevision;
  }
  if (frame.topic === "/pulso/hil/action_result") {
    const history = actionHistory.get(payload.action_id) ?? [];
    history.push(payload);
    actionHistory.set(payload.action_id, history);
  }
});

socket.addEventListener("error", () => {
  clearTimeout(deadline);
  clearInterval(perceptionTimer);
  process.exitCode = 1;
});
