#!/usr/bin/env node

/**
 * Capture one strict, non-mock PULSO run from rosbridge.
 *
 * This observer never publishes commands or synthetic sensor data. A passing
 * report therefore proves that the running Gemma brain selected an action,
 * the real navigation stack executed it, and the public audit stream matches
 * the exact multimodal input reported by the runtime.
 */

import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const TERMINAL = new Set([
  "SUCCEEDED", "BLOCKED", "CANCELLED", "REJECTED", "TIMEOUT",
  "ACTUATOR_TIMEOUT", "BUSY", "INVALID_CONTRACT", "INVALID_TARGET",
  "INVALID_CAPABILITY", "STALE_OR_UNKNOWN_TARGET", "STALE_CAPABILITY",
  "EXPIRED_CAPABILITY", "STALE_NAVIGATION_REVISION", "STALE_TRACKING_EPOCH",
  "STALE_TARGET_REVISION", "TARGET_TYPE_MISMATCH", "LOCALIZATION_UNAVAILABLE",
  "TARGET_TOO_CLOSE",
  "UNSUPPORTED_ACTION", "ACTION_RESULT_TIMEOUT",
]);

const MOTION_ACTIONS = new Set(["MOVE_TO", "LOOK_AT"]);

const TOPICS = Object.freeze({
  observation: "/pulso/hil/observation",
  candidates: "/pulso/navigation/candidates",
  actionIntent: "/pulso/hil/action_intent",
  actionResult: "/pulso/hil/action_result",
  scene: "/pulso/navigation/metaview_scene",
  tracks: "/pulso/hil/perception_tracks",
  perception: "/pulso/hil/perception_telemetry",
  trace: "/pulso/hil/brain_trace",
  gemmaInput: "/pulso/hil/gemma_input",
  gemmaView: "/pulso/hil/gemma_view/compressed",
});

const STRING_TOPICS = new Set(Object.values(TOPICS).filter((topic) => topic !== TOPICS.gemmaView));

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function distanceM(before, after) {
  if (!before || !after) return null;
  return Math.hypot(Number(after.x) - Number(before.x), Number(after.y) - Number(before.y));
}

function monotonicNs(value) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number >= 0 ? number : null;
}

function firstSettledObservation(observations, afterNs, beforeNs = null) {
  return observations
    .filter((observation) => {
      const capturedNs = monotonicNs(observation.captured_monotonic_ns);
      return observation.motion_state === "STOPPED"
        && capturedNs !== null
        && capturedNs >= afterNs
        && (beforeNs === null || capturedNs < beforeNs);
    })
    .sort((left, right) => left.captured_monotonic_ns - right.captured_monotonic_ns)[0] ?? null;
}

export function beginMoveMeasurement(action, terminalResult, terminalPoseSnapshot) {
  if (action.intent?.kind !== "MOVE_TO") return;
  const terminalNs = monotonicNs(terminalResult.captured_monotonic_ns);
  action.terminal_pose_snapshot = terminalPoseSnapshot;
  action.displacement_measurement = {
    method: "FIRST_STOPPED_OBSERVATION_AFTER_TERMINAL",
    status: terminalNs === null ? "MISSING_TERMINAL_MONOTONIC_NS" : "AWAITING_STOPPED",
    terminal_status: terminalResult.status,
    terminal_captured_monotonic_ns: terminalNs,
    next_motion_active_monotonic_ns: null,
    settled_captured_monotonic_ns: null,
  };
}

export function markNextMotionBoundary(evidence, nextActionId, activeResult) {
  const boundaryNs = monotonicNs(activeResult.captured_monotonic_ns);
  if (boundaryNs === null) return;
  const nextKind = evidence.actions[nextActionId]?.intent?.kind;
  if (!MOTION_ACTIONS.has(nextKind)) return;

  for (const [actionId, action] of Object.entries(evidence.actions)) {
    const measurement = action.displacement_measurement;
    if (actionId === nextActionId || measurement?.status !== "AWAITING_STOPPED") continue;
    const terminalNs = measurement.terminal_captured_monotonic_ns;
    if (terminalNs !== null && boundaryNs >= terminalNs) {
      measurement.next_motion_active_monotonic_ns = boundaryNs;
    }
  }
}

export function bindSettledMoveMeasurements(evidence) {
  for (const action of Object.values(evidence.actions)) {
    const measurement = action.displacement_measurement;
    if (measurement?.status !== "AWAITING_STOPPED") continue;
    const settled = firstSettledObservation(
      evidence.observations,
      measurement.terminal_captured_monotonic_ns,
      measurement.next_motion_active_monotonic_ns,
    );
    if (settled) {
      action.pose_after = settled;
      action.displacement_m = distanceM(action.pose_before, action.pose_after);
      measurement.status = "BOUND_STOPPED";
      measurement.settled_captured_monotonic_ns = settled.captured_monotonic_ns;
    } else if (measurement.next_motion_active_monotonic_ns !== null) {
      measurement.status = "SUPERSEDED_BY_NEXT_MOTION";
    }
  }
}

function hasAuditedSettledMeasurement(action) {
  const measurement = action.displacement_measurement;
  const terminalNs = monotonicNs(measurement?.terminal_captured_monotonic_ns);
  const settledNs = monotonicNs(measurement?.settled_captured_monotonic_ns);
  const poseNs = monotonicNs(action.pose_after?.captured_monotonic_ns);
  const measuredDistance = distanceM(action.pose_before, action.pose_after);
  return measurement?.method === "FIRST_STOPPED_OBSERVATION_AFTER_TERMINAL"
    && measurement.status === "BOUND_STOPPED"
    && action.pose_after?.motion_state === "STOPPED"
    && terminalNs !== null
    && settledNs !== null
    && poseNs === settledNs
    && settledNs >= terminalNs
    && Number.isFinite(action.displacement_m)
    && measuredDistance !== null
    && Math.abs(action.displacement_m - measuredDistance) < 1e-9;
}

export function evaluateEvidence(evidence) {
  const failures = [];
  const worldInputs = evidence.gemma_inputs.filter((item) => item.input_kind === "WORLD_PACKET");
  const imageInputs = worldInputs.filter((item) => item.image);
  const matchedImages = evidence.gemma_views.filter(
    (item) => item.matched_input_id && item.metadata_match === true,
  );
  const moveRequests = evidence.brain_trace.filter(
    (item) => item.category === "TOOL_REQUEST" && item.label === "move_to",
  );
  const requestViewResults = evidence.brain_trace.filter(
    (item) => item.category === "TOOL_RESULT"
      && item.label === "request_view"
      && item.attributes?.image_ready_next_turn === true,
  );
  const successfulMoves = Object.values(evidence.actions).filter((action) =>
    action.intent?.kind === "MOVE_TO"
      && action.statuses.includes("ACTIVE")
      && action.statuses.includes("SUCCEEDED"),
  );
  const settledMoves = successfulMoves.filter(
    hasAuditedSettledMeasurement,
  );
  const moved = settledMoves.some((action) => (action.displacement_m ?? 0) >= 0.05);
  const completedTurns = new Set(
    evidence.brain_trace
      .filter((item) => item.category === "CYCLE_COMPLETE")
      .map((item) => item.turn_id),
  );
  const moveTurnCompleted = moveRequests.some((request) => completedTurns.has(request.turn_id));
  const validRuntimeHashes = evidence.gemma_inputs.every((item) => item.runtime_hashes_valid === true);
  const livePerception = evidence.perception_telemetry.some((item) =>
    item.model_id === "yolo11n-pose-onnx"
      && item.provider === "CUDAExecutionProvider"
      && item.status === "LIVE",
  );
  const usableScene = evidence.metaview_scenes.some((item) =>
    item.known_cells > 0 && item.route_count > 0 && item.depth_sample_count > 0,
  );

  if (!worldInputs.length) failures.push("No WORLD_PACKET exacto fue publicado por Gemma.");
  if (!validRuntimeHashes) failures.push("El system prompt o los tool schemas no coinciden con sus SHA-256.");
  if (!moveRequests.length) failures.push("Gemma no pidió move_to.");
  if (!successfulMoves.length) failures.push("No existe MOVE_TO con estados ACTIVE→SUCCEEDED.");
  if (!moved) failures.push("El MOVE_TO no produjo al menos 5 cm de desplazamiento VIO medido.");
  if (!moveTurnCompleted) failures.push("El turno que pidió movimiento no llegó a CYCLE_COMPLETE.");
  if (!requestViewResults.length) failures.push("Gemma no completó request_view con una imagen fresca para el siguiente turno.");
  if (!imageInputs.length) failures.push("Ningún WORLD_PACKET incluyó imagen solicitada.");
  if (!matchedImages.length) failures.push("Ningún JPEG auditado coincide en bytes y SHA-256 con la entrada de Gemma.");
  if (!livePerception) failures.push("No se observó YOLO11n-pose LIVE sobre CUDAExecutionProvider.");
  if (!usableScene) failures.push("MetaView no publicó simultáneamente mapa, rutas y depth 3D reales.");

  return {
    ok: failures.length === 0,
    failures,
    metrics: {
      world_packets: worldInputs.length,
      image_world_packets: imageInputs.length,
      matched_gemma_views: matchedImages.length,
      move_tool_requests: moveRequests.length,
      successful_move_actions: successfulMoves.length,
      settled_move_measurements: settledMoves.length,
      maximum_move_displacement_m: Math.max(0, ...settledMoves.map((item) => item.displacement_m ?? 0)),
      request_view_results: requestViewResults.length,
      completed_turns: completedTurns.size,
      perception_samples: evidence.perception_telemetry.length,
      scene_samples: evidence.metaview_scenes.length,
    },
  };
}

export function createEvidence(url) {
  return {
    contract_version: "pulso.e2e-evidence.v1",
    source: "ROSBRIDGE_READ_ONLY",
    mock_data_published: false,
    rosbridge_url: url,
    started_at: new Date().toISOString(),
    finished_at: null,
    latest_navigation: null,
    observations: [],
    gemma_inputs: [],
    gemma_views: [],
    brain_trace: [],
    actions: {},
    perception_telemetry: [],
    perception_tracks: [],
    metaview_scenes: [],
    result: null,
  };
}

export function summarizeScene(payload) {
  return {
    captured_monotonic_ns: payload.captured_monotonic_ns ?? null,
    sensor_map_seq: payload.sensor_map_seq ?? null,
    navigation_revision: payload.navigation_revision ?? null,
    known_cells: payload.map?.known_cells ?? 0,
    free_point_count: payload.map?.free_points_m?.length ?? 0,
    occupied_point_count: payload.map?.occupied_points_m?.length ?? 0,
    depth_sample_count: payload.depth?.sample_count ?? 0,
    scan_footprint_points: payload.scan_footprint_m?.length ?? 0,
    route_count: payload.routes?.length ?? 0,
    route_ids: (payload.routes ?? []).map((item) => item.id),
    selected_route_id: (payload.routes ?? []).find((item) => item.selected)?.id ?? null,
    robot: payload.robot ?? null,
  };
}

function parseStdString(message) {
  if (typeof message?.data !== "string") return null;
  try {
    const parsed = JSON.parse(message.data);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function poseFromObservation(payload) {
  const position = payload.robot?.pose?.position_m;
  if (!Array.isArray(position) || position.length < 2) return null;
  return {
    captured_monotonic_ns: payload.captured_monotonic_ns ?? null,
    x: Number(position[0]),
    y: Number(position[1]),
    heading_deg: Number(payload.robot?.pose?.heading_deg ?? 0),
    motion_state: payload.robot?.motion_state ?? "UNKNOWN",
  };
}

function canonicalInput(payload) {
  const computedSystem = sha256(Buffer.from(payload.system_prompt ?? "", "utf8"));
  const computedTools = sha256(Buffer.from(stableJson(payload.tool_schemas ?? []), "utf8"));
  return {
    ...payload,
    runtime_hashes_valid:
      computedSystem === payload.system_prompt_sha256
      && computedTools === payload.tool_schemas_sha256,
    computed_system_prompt_sha256: computedSystem,
    computed_tool_schemas_sha256: computedTools,
  };
}

function trimPush(collection, value, maximum = 600) {
  collection.push(value);
  if (collection.length > maximum) collection.splice(0, collection.length - maximum);
}

async function runCapture({ url, outputDir, timeoutMs }) {
  await mkdir(outputDir, { recursive: true });
  const evidence = createEvidence(url);
  const socket = new WebSocket(url);
  let latestPose = null;
  let completed = false;
  let messageQueue = Promise.resolve();

  const finish = async (reason, { drain = true } = {}) => {
    if (completed) return;
    completed = true;
    if (drain) await messageQueue;
    evidence.finished_at = new Date().toISOString();
    evidence.result = evaluateEvidence(evidence);
    evidence.stop_reason = reason;
    const reportPath = path.join(outputDir, "e2e-report.json");
    await writeFile(reportPath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
    console.log(JSON.stringify({
      report: reportPath,
      ...evidence.result,
    }, null, 2));
    try { socket.close(1000, reason); } catch {}
    process.exitCode = evidence.result.ok ? 0 : 1;
  };

  const deadline = setTimeout(() => void finish("timeout"), timeoutMs);

  socket.addEventListener("open", () => {
    for (const topic of Object.values(TOPICS)) {
      socket.send(JSON.stringify({
        op: "subscribe",
        id: `e2e-${topic}`,
        topic,
        type: topic === TOPICS.gemmaView
          ? "sensor_msgs/msg/CompressedImage"
          : "std_msgs/msg/String",
        throttle_rate: topic === TOPICS.scene ? 350 : 0,
        queue_length: topic === TOPICS.scene ? 1 : 20,
      }));
    }
  });

  socket.addEventListener("message", (event) => {
    messageQueue = messageQueue.then(async () => {
      let frame;
      try { frame = JSON.parse(event.data); } catch { return; }
      if (frame.op !== "publish" || !Object.values(TOPICS).includes(frame.topic)) return;

      if (frame.topic === TOPICS.gemmaView) {
        const bytes = Buffer.from(frame.msg?.data ?? "", "base64");
        const digest = sha256(bytes);
        const input = [...evidence.gemma_inputs].reverse().find((item) =>
          item.image?.jpeg_sha256 === digest
            && !evidence.gemma_views.some((view) => view.matched_input_id === item.input_id),
        );
        const filename = input ? `gemma-view-${input.input_id}.jpg` : `gemma-view-unmatched-${Date.now()}.jpg`;
        await writeFile(path.join(outputDir, filename), bytes);
        trimPush(evidence.gemma_views, {
          received_at: new Date().toISOString(),
          matched_input_id: input?.input_id ?? null,
          turn_id: input?.turn_id ?? null,
          sha256: digest,
          byte_length: bytes.length,
          metadata_match: Boolean(input)
            && input.image.byte_length === bytes.length
            && input.image.jpeg_sha256 === digest,
          file: filename,
        });
        return;
      }

      if (!STRING_TOPICS.has(frame.topic)) return;
      const payload = parseStdString(frame.msg);
      if (!payload) return;
      const receivedAt = new Date().toISOString();

      if (frame.topic === TOPICS.observation) {
        const pose = poseFromObservation(payload);
        if (!pose) return;
        latestPose = pose;
        trimPush(evidence.observations, pose);
        bindSettledMoveMeasurements(evidence);
      } else if (frame.topic === TOPICS.candidates) {
        evidence.latest_navigation = {
          received_at: receivedAt,
          sensor_map_seq: payload.sensor_map_seq ?? null,
          navigation_revision: payload.navigation_revision ?? null,
          candidate_ids: (payload.candidates ?? []).map((item) => `${item.type}:${item.id}`),
        };
      } else if (frame.topic === TOPICS.actionIntent) {
        const actionId = payload.action_id;
        if (!actionId) return;
        const action = evidence.actions[actionId] ?? { statuses: [] };
        action.intent = payload;
        action.received_at = receivedAt;
        action.pose_before = latestPose;
        evidence.actions[actionId] = action;
      } else if (frame.topic === TOPICS.actionResult) {
        const actionId = payload.action_id;
        if (!actionId) return;
        const action = evidence.actions[actionId] ?? { statuses: [], pose_before: latestPose };
        if (!action.statuses.includes(payload.status)) action.statuses.push(payload.status);
        action.results = [...(action.results ?? []), { received_at: receivedAt, ...payload }];
        if (payload.status === "ACTIVE") {
          evidence.actions[actionId] = action;
          markNextMotionBoundary(evidence, actionId, payload);
          bindSettledMoveMeasurements(evidence);
        }
        if (TERMINAL.has(payload.status)) {
          if (action.intent?.kind === "MOVE_TO") {
            beginMoveMeasurement(action, payload, latestPose);
            evidence.actions[actionId] = action;
            bindSettledMoveMeasurements(evidence);
          } else {
            action.pose_after = latestPose;
            action.displacement_m = distanceM(action.pose_before, action.pose_after);
          }
        }
        evidence.actions[actionId] = action;
      } else if (frame.topic === TOPICS.gemmaInput) {
        trimPush(evidence.gemma_inputs, canonicalInput({ received_at: receivedAt, ...payload }), 80);
      } else if (frame.topic === TOPICS.trace) {
        trimPush(evidence.brain_trace, { received_at: receivedAt, ...payload }, 300);
      } else if (frame.topic === TOPICS.perception) {
        trimPush(evidence.perception_telemetry, { received_at: receivedAt, ...payload }, 120);
      } else if (frame.topic === TOPICS.tracks) {
        trimPush(evidence.perception_tracks, {
          received_at: receivedAt,
          captured_monotonic_ns: payload.captured_monotonic_ns ?? null,
          frame_id: payload.frame_id ?? null,
          tracks: payload.tracks ?? [],
        }, 120);
      } else if (frame.topic === TOPICS.scene) {
        trimPush(evidence.metaview_scenes, { received_at: receivedAt, ...summarizeScene(payload) }, 120);
      }

      const result = evaluateEvidence(evidence);
      if (result.ok) {
        clearTimeout(deadline);
        await finish("all_strict_assertions_satisfied", { drain: false });
      }
    }).catch(async (error) => {
      evidence.observer_error = error instanceof Error ? error.stack : String(error);
      clearTimeout(deadline);
      await finish("observer_error", { drain: false });
    });
  });

  socket.addEventListener("error", async () => {
    clearTimeout(deadline);
    await finish("websocket_error");
  });

  socket.addEventListener("close", async () => {
    if (!completed) {
      clearTimeout(deadline);
      await finish("websocket_closed");
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const url = process.argv[2] ?? "ws://192.168.18.51:9091";
  const outputDir = process.argv[3]
    ? path.resolve(process.argv[3])
    : path.join(projectRoot, "sim", "logs", "e2e", new Date().toISOString().replaceAll(":", "-"));
  const timeoutMs = Number(process.argv[4] ?? 240_000);
  await runCapture({ url, outputDir, timeoutMs });
}
