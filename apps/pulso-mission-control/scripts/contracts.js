import { parseCameraInfo, parsePhoneTelemetry } from "./phone-contracts.js";

export { parseCameraInfo, parsePhoneTelemetry };

const ROS_TOPICS = Object.freeze({
  observation: "/pulso/hil/observation",
  candidates: "/pulso/navigation/candidates",
  actionResult: "/pulso/hil/action_result",
  metaView: "/pulso/navigation/metaview/compressed",
  metaViewScene: "/pulso/navigation/metaview_scene",
  camera: "/pulso/phone/rgb/compressed",
  phoneTelemetry: "/pulso/phone/telemetry",
  cameraInfo: "/pulso/phone/rgb/camera_info",
  perceptionTracks: "/pulso/hil/perception_tracks",
  brainTrace: "/pulso/hil/brain_trace",
  gemmaInput: "/pulso/hil/gemma_input",
  gemmaView: "/pulso/hil/gemma_view/compressed",
  perceptionTelemetry: "/pulso/hil/perception_telemetry",
});

export const SUBSCRIPTIONS = Object.freeze([
  [ROS_TOPICS.observation, "std_msgs/msg/String", 0],
  [ROS_TOPICS.candidates, "std_msgs/msg/String", 0],
  [ROS_TOPICS.actionResult, "std_msgs/msg/String", 0],
  [ROS_TOPICS.metaView, "sensor_msgs/msg/CompressedImage", 250],
  [ROS_TOPICS.metaViewScene, "std_msgs/msg/String", 0],
  [ROS_TOPICS.camera, "sensor_msgs/msg/CompressedImage", 250],
  [ROS_TOPICS.phoneTelemetry, "std_msgs/msg/String", 250],
  // The physical S25 publishes the auditable JSON contract while Gazebo owns
  // this same parity topic as sensor_msgs/CameraInfo. Omit the requested type
  // so rosbridge binds to whichever real publisher is active.
  [ROS_TOPICS.cameraInfo, null, 1_000],
  [ROS_TOPICS.perceptionTracks, "std_msgs/msg/String", 0],
  [ROS_TOPICS.brainTrace, "std_msgs/msg/String", 0],
  [ROS_TOPICS.gemmaInput, "std_msgs/msg/String", 0],
  [ROS_TOPICS.gemmaView, "sensor_msgs/msg/CompressedImage", 0],
  [ROS_TOPICS.perceptionTelemetry, "std_msgs/msg/String", 0],
]);

export { ROS_TOPICS };

export function parseRosbridgeFrame(rawFrame) {
  const outer = typeof rawFrame === "string" ? safeJson(rawFrame) : rawFrame;
  if (!isObject(outer)) return null;
  if (outer.op === "status") {
    return {
      kind: "bridge-status",
      level: asString(outer.level) || "info",
      message: asString(outer.msg) || "Rosbridge status",
    };
  }
  if (outer.op !== "publish" || !isObject(outer.msg) || !asString(outer.topic)) return null;
  const topic = outer.topic;
  if (topic === ROS_TOPICS.metaView || topic === ROS_TOPICS.camera || topic === ROS_TOPICS.gemmaView) {
    return parseCompressedImage(topic, outer.msg);
  }
  if (topic === ROS_TOPICS.cameraInfo) {
    const stringPayload = parseStdString(outer.msg);
    return parseCameraInfo(stringPayload ?? outer.msg);
  }
  const payload = parseStdString(outer.msg);
  if (!payload) return null;
  if (topic === ROS_TOPICS.observation) return parseObservation(payload);
  if (topic === ROS_TOPICS.candidates) return parseCandidates(payload);
  if (topic === ROS_TOPICS.metaViewScene) return parseMetaviewScene(payload);
  if (topic === ROS_TOPICS.actionResult) return parseActionResult(payload);
  if (topic === ROS_TOPICS.perceptionTracks) return parsePerceptionTracks(payload);
  if (topic === ROS_TOPICS.brainTrace) return parseBrainTrace(payload);
  if (topic === ROS_TOPICS.gemmaInput) return parseGemmaInput(payload);
  if (topic === ROS_TOPICS.perceptionTelemetry) return parsePerceptionTelemetry(payload);
  if (topic === ROS_TOPICS.phoneTelemetry) return parsePhoneTelemetry(payload);
  return null;
}

export function parseObservation(payload) {
  const value = asPayload(payload);
  const robot = value?.robot;
  const pose = robot?.pose;
  const position = pose?.position_m;
  if (!isObject(value) || !isObject(robot) || !Array.isArray(position) || position.length < 2) {
    return null;
  }
  return {
    kind: "observation",
    observationId: asString(value.observation_id) || "unknown",
    source: asString(value.source) || "UNKNOWN",
    capturedNs: asFinite(value.captured_monotonic_ns),
    tracking: {
      state: asString(value.tracking?.state) || "UNKNOWN",
      quality: asFinite(value.tracking?.quality),
      epoch: asFinite(value.tracking?.epoch),
    },
    robot: {
      x: asFinite(position[0]),
      y: asFinite(position[1]),
      z: asFinite(position[2]),
      headingDeg: asFinite(pose.heading_deg),
      confidence: asFinite(pose.confidence),
      motionState: asString(robot.motion_state) || "UNKNOWN",
      batteryFraction: asFinite(robot.battery_fraction),
      flashlightOn: robot.flashlight_on === true,
      frontRangeM: asFinite(robot.front_range_m),
      bumperPressed: robot.bumper_pressed === true,
    },
    artifacts: Array.isArray(value.artifacts) ? value.artifacts.filter(isObject) : [],
  };
}

export function parseCandidates(payload) {
  const value = asPayload(payload);
  if (!isObject(value) || !Array.isArray(value.candidates)) return null;
  return {
    kind: "candidates",
    capturedNs: asFinite(value.captured_monotonic_ns),
    sensorMapSeq: asFinite(value.sensor_map_seq),
    navigationRevision: asFinite(value.navigation_revision),
    validUntilNs: asFinite(value.valid_until_monotonic_ns),
    candidates: value.candidates.map((candidate, index) => normalizeCandidate(candidate, index)),
  };
}

export function parseActionResult(payload) {
  const value = asPayload(payload);
  if (!isObject(value) || !asString(value.action_id)) return null;
  return {
    kind: "action-result",
    actionId: value.action_id,
    accepted: value.accepted === true,
    status: asString(value.status) || "UNKNOWN",
    detail: asString(value.detail) || "Sin detalle",
    capturedNs: asFinite(value.captured_monotonic_ns),
    data: isObject(value.data) ? value.data : {},
  };
}

export function parsePerceptionTracks(payload) {
  const value = asPayload(payload);
  if (!isObject(value) || !Array.isArray(value.tracks)) return null;
  const tracks = value.tracks.map(normalizeTrack).filter(Boolean);
  return {
    kind: "perception-tracks",
    capturedNs: asFinite(value.captured_monotonic_ns),
    frameId: asString(value.frame_id) || "unknown",
    tracks,
  };
}

export function parseBrainTrace(payload) {
  const value = asPayload(payload);
  if (!isObject(value)) return null;
  const attributes = isObject(value.attributes) ? value.attributes : {};
  const summary = asString(value.summary) || asString(value.detail) || asString(value.text);
  const category = asString(value.category) || asString(value.stage);
  if (!summary || !category) return null;
  return {
    kind: "brain-trace",
    turnId: asString(value.turn_id) || "unknown-turn",
    worldSeq: asFinite(value.world_seq ?? value.selected_world_seq),
    category: category.toUpperCase(),
    label: asString(value.label) || category.toUpperCase(),
    summary,
    latencyMs: asFinite(value.latency_ms),
    capturedNs: asFinite(value.captured_monotonic_ns),
    skillId: asString(value.skill_id) || asString(attributes.skill_id),
    skillState: asString(value.skill_state) || inferredSkillState(category, value.label, attributes),
    activeSkillId: asString(value.active_skill_id) || asString(attributes.active_skill_id),
    goal: asString(value.goal) || asString(attributes.goal_id),
    checkpoint: asString(value.checkpoint) || asString(attributes.checkpoint),
    question: asString(value.question) || asString(attributes.question),
    decisionNeed: asString(value.decision_need) || asString(attributes.decision_need),
    planSummary: asString(value.plan_summary) || asString(attributes.plan_summary),
    contextTokens: asFinite(value.context_tokens),
    attributes,
  };
}

export function parsePerceptionTelemetry(payload) {
  const value = asPayload(payload);
  if (!isObject(value) || !asString(value.model_id)) return null;
  return {
    kind: "perception-telemetry",
    modelId: value.model_id,
    provider: asString(value.provider),
    status: (asString(value.status) || "UNKNOWN").toUpperCase(),
    count: asFinite(value.count ?? value.detection_count),
    latencyMs: asFinite(value.latency_ms ?? value.inference_latency_ms),
    frameAgeMs: asFinite(value.frame_age_ms),
    revision: asFinite(value.revision ?? value.semantic_revision),
    capturedNs: asFinite(
      value.captured_monotonic_ns ?? value.published_monotonic_ns ?? value.source_capture_ns,
    ),
  };
}

export function parseGemmaInput(payload) {
  const value = asPayload(payload);
  if (!isObject(value) || !asString(value.turn_id) || !asString(value.model_id)) return null;
  const exactMessage = isObject(value.exact_message) ? value.exact_message : null;
  const image = isObject(value.image) ? value.image : null;
  return {
    kind: "gemma-input",
    inputId: asString(value.input_id) || "unknown-input",
    turnId: value.turn_id,
    worldSeq: asFinite(value.selected_world_seq),
    modelId: value.model_id,
    backend: asString(value.backend),
    inputKind: asString(value.input_kind) || "UNKNOWN",
    exactMessage,
    promptText: typeof value.prompt_text === "string" ? value.prompt_text : null,
    systemPrompt: typeof value.system_prompt === "string" ? value.system_prompt : null,
    systemPromptSha256: asString(value.system_prompt_sha256),
    toolSchemas: Array.isArray(value.tool_schemas) ? value.tool_schemas : [],
    toolSchemasSha256: asString(value.tool_schemas_sha256),
    contextTokensBefore: asFinite(value.context_tokens_before),
    conversationScope: asString(value.conversation_scope)
      || (value.conversation_reused_across_turns === false ? "TURN" : null),
    conversationReusedAcrossTurns: value.conversation_reused_across_turns === true,
    image: image ? {
      kind: asString(image.kind),
      sourceTopic: asString(image.source_topic),
      capturedNs: asFinite(image.captured_monotonic_ns),
      format: asString(image.format),
      sha256: asString(image.jpeg_sha256),
      byteLength: asFinite(image.byte_length),
      auditTopic: asString(image.audit_topic),
    } : null,
    publishedNs: asFinite(value.published_monotonic_ns),
  };
}

export function parseMetaviewScene(payload) {
  const value = asPayload(payload);
  if (!isObject(value) || value.contract_version !== "pulso.metaview-scene.v1") return null;
  const map = isObject(value.map) ? value.map : {};
  const robot = isObject(value.robot) ? value.robot : {};
  const depth = isObject(value.depth) ? value.depth : {};
  const position = point3(robot.position_m);
  if (!position) return null;
  return {
    kind: "metaview-scene",
    capturedNs: asFinite(value.captured_monotonic_ns),
    frameId: asString(value.frame_id) || "map",
    mapSeq: asFinite(value.sensor_map_seq),
    navigationRevision: asFinite(value.navigation_revision),
    map: {
      resolutionM: asFinite(map.resolution_m),
      origin: point2(map.origin_m),
      width: asFinite(map.width),
      height: asFinite(map.height),
      knownCells: asFinite(map.known_cells),
      unknownCells: asFinite(map.unknown_cells),
      freePoints: points2(map.free_points_m, 5_000),
      occupiedPoints: points2(map.occupied_points_m, 5_000),
    },
    robot: {
      position,
      headingDeg: asFinite(robot.heading_deg) ?? 0,
    },
    depth: {
      source: asString(depth.source),
      frameId: asString(depth.frame_id) || "map",
      points: points3(depth.points_m, 2_000),
      sampleCount: asFinite(depth.sample_count),
    },
    scanFootprint: points3(value.scan_footprint_m, 256),
    routes: Array.isArray(value.routes)
      ? value.routes.slice(0, 6).map(normalizeSceneRoute).filter(Boolean)
      : [],
    bounds: finiteArray(value.bounds_m, 4),
  };
}

function parseCompressedImage(topic, message) {
  const data = asString(message.data);
  if (!data) return null;
  const stamp = message.header?.stamp;
  const seconds = asFinite(stamp?.sec);
  const nanoseconds = asFinite(stamp?.nanosec);
  return {
    kind: topic === ROS_TOPICS.metaView
      ? "metaview-image"
      : topic === ROS_TOPICS.gemmaView ? "gemma-view-image" : "camera-image",
    base64: data,
    format: asString(message.format) || "jpeg",
    capturedNs: seconds === null ? null : seconds * 1_000_000_000 + (nanoseconds || 0),
  };
}

function parseStdString(message) {
  const data = asString(message.data);
  return data ? safeJson(data) : null;
}

function normalizeCandidate(candidate, index) {
  const position = Array.isArray(candidate?.position_m) ? candidate.position_m : [];
  return {
    type: asString(candidate?.type) || "UNKNOWN",
    id: asString(candidate?.id) || `candidate-${index}`,
    label: asString(candidate?.label) || `Ruta ${String.fromCharCode(65 + index)}`,
    purpose: asString(candidate?.purpose) || "Sin propósito reportado",
    x: asFinite(position[0]),
    y: asFinite(position[1]),
    pathLengthM: asFinite(candidate?.path_length_m),
    risk: asFinite(candidate?.risk),
    informationGain: asFinite(candidate?.information_gain),
    frontierCells: asFinite(candidate?.frontier_cells),
  };
}

function normalizeTrack(track) {
  if (!isObject(track)) return null;
  const box = Array.isArray(track.box_norm) ? track.box_norm.map(asFinite) : [];
  return {
    id: asString(track.id) || "untracked",
    label: asString(track.label) || "unknown",
    confidence: asFinite(track.confidence),
    bearingDeg: asFinite(track.bearing_deg),
    boxNorm: box.length === 4 && box.every((value) => value !== null) ? box : null,
    revision: asFinite(track.revision),
    modelId: asString(track.model_id),
    inferenceLatencyMs: asFinite(track.inference_latency_ms),
    visibleKeypoints: asFinite(track.visible_keypoints),
  };
}

function normalizeSceneRoute(route) {
  if (!isObject(route) || !asString(route.id)) return null;
  return {
    id: route.id,
    type: asString(route.type) || "UNKNOWN",
    label: asString(route.label),
    selected: route.selected === true,
    position: point3(route.position_m),
    path: points3(route.path_m, 512),
    risk: asFinite(route.risk),
    informationGain: asFinite(route.information_gain),
  };
}

function points2(value, maximum) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, maximum).map(point2).filter(Boolean);
}

function points3(value, maximum) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, maximum).map(point3).filter(Boolean);
}

function point2(value) {
  const result = finiteArray(value, 2);
  return result?.slice(0, 2) || null;
}

function point3(value) {
  const result = finiteArray(value, 2);
  if (!result) return null;
  return [result[0], result[1], asFinite(value[2]) ?? 0];
}

function finiteArray(value, minimum) {
  if (!Array.isArray(value) || value.length < minimum) return null;
  const result = value.map(asFinite);
  return result.every((item) => item !== null) ? result : null;
}

function inferredSkillState(category, label, attributes) {
  if (asString(label)?.toLowerCase() !== "load_skill" || !asString(attributes.skill_id)) return null;
  if (category.toUpperCase() !== "TOOL_RESULT") return "waiting";
  const status = asString(attributes.status)?.toUpperCase();
  return status === "SKILL_LOADED" || status === "SUCCEEDED" ? "loaded" : "waiting";
}

function asPayload(value) {
  if (typeof value === "string") return safeJson(value);
  return isObject(value) ? value : null;
}

function safeJson(value) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function asString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asFinite(value) {
  const number = typeof value === "string" && value.trim() ? Number(value) : value;
  return Number.isFinite(number) ? number : null;
}
