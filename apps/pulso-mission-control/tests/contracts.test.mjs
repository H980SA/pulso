import assert from "node:assert/strict";
import test from "node:test";

import {
  parseActionResult,
  parseBrainTrace,
  parseCandidates,
  parseGemmaInput,
  parseMetaviewScene,
  parseObservation,
  parsePhoneTelemetry,
  parseCameraInfo,
  parsePerceptionTelemetry,
  parseRosbridgeFrame,
} from "../scripts/contracts.js";
import { resolveBridgeUrl } from "../scripts/rosbridge.js";
import { buildCamera, projectPoint } from "../scripts/spatial-map.js";
import { createMissionStore } from "../scripts/store.js";

test("normalizes the live observation contract without manufacturing fields", () => {
  const event = parseObservation({
    observation_id: "OBS-17",
    source: "GAZEBO_HIL",
    captured_monotonic_ns: 1700,
    tracking: { state: "TRACKING", quality: 0.91, epoch: 3 },
    robot: {
      pose: { position_m: [3.06, -0.52, 0.11], heading_deg: 24, confidence: 0.88 },
      motion_state: "STOPPED",
      battery_fraction: 0.8,
      flashlight_on: false,
      front_range_m: null,
    },
  });
  assert.equal(event.kind, "observation");
  assert.equal(event.robot.x, 3.06);
  assert.equal(event.robot.frontRangeM, null);
  assert.equal(event.tracking.state, "TRACKING");
});

test("accepts only versioned real phone telemetry with measured nullable vectors", () => {
  const payload = {
    contract_version: "pulso.phone-telemetry.v1",
    captured_monotonic_ns: 8_000,
    source: "ANDROID_REAL",
    frame_id: "phone_device",
    imu: {
      captured_monotonic_ns: 7_990,
      acceleration_mps2: [0.1, 0.2, 9.7],
      angular_velocity_radps: null,
    },
    battery: { fraction: 0.72, temperature_c: 37.5 },
  };
  const event = parsePhoneTelemetry(payload);
  assert.equal(event.kind, "phone-telemetry");
  assert.deepEqual(event.accelerationMps2, [0.1, 0.2, 9.7]);
  assert.equal(event.angularVelocityRadps, null);
  assert.equal(event.batteryTemperatureC, 37.5);
  assert.equal(parsePhoneTelemetry({ contract_version: "pulso.phone-telemetry.v0" }), null);
  const bridged = parseRosbridgeFrame({
    op: "publish",
    topic: "/pulso/phone/telemetry",
    msg: { data: JSON.stringify(payload) },
  });
  const store = createMissionStore();
  store.ingest(bridged, 9, { topic: "/pulso/phone/telemetry" });
  assert.equal(store.get().phoneTelemetry.imuCapturedNs, 7_990);
  assert.equal(store.get().events.at(-1).kind, "phone-telemetry");
});

test("parses and retains versioned ARCore camera intrinsics", () => {
  const event = parseCameraInfo({
    contract_version: "pulso.phone-camera-info.v1",
    captured_monotonic_ns: 8_000,
    frame_id: "phone_rgb_optical_frame",
    calibration_source: "arcore/image_intrinsics",
    width: 1920,
    height: 1080,
    model: "pinhole",
    distortion_model: "not_reported",
    k: [612, 0, 960, 0, 611, 540, 0, 0, 1],
  });
  assert.equal(event.kind, "phone-camera-info");
  assert.equal(event.k[0], 612);
  const store = createMissionStore();
  store.ingest(event, 10, { topic: "/pulso/phone/rgb/camera_info" });
  assert.equal(store.get().cameraInfo.width, 1920);
  assert.equal(store.get().events.at(-1).topic, "/pulso/phone/rgb/camera_info");
});

test("accepts the same camera-info topic from Gazebo without forcing the physical JSON type", () => {
  const event = parseRosbridgeFrame({
    op: "publish",
    topic: "/pulso/phone/rgb/camera_info",
    msg: {
      header: { stamp: { sec: 12, nanosec: 34 }, frame_id: "phone_rgb_optical_frame" },
      height: 720,
      width: 1280,
      distortion_model: "plumb_bob",
      k: [554, 0, 640, 0, 554, 360, 0, 0, 1],
    },
  });
  assert.equal(event.kind, "phone-camera-info");
  assert.equal(event.contractVersion, "sensor_msgs/msg/CameraInfo");
  assert.equal(event.calibrationSource, "ros/camera_info");
  assert.equal(event.capturedNs, 12_000_000_034);
  assert.equal(event.width, 1280);
});

test("keeps candidate labels, spatial endpoints, and planner scores", () => {
  const event = parseCandidates({
    captured_monotonic_ns: 8,
    sensor_map_seq: 7,
    navigation_revision: 12,
    valid_until_monotonic_ns: 99,
    candidates: [{
      type: "FRONTIER",
      id: "FR-021",
      label: "Camino A",
      purpose: "Expandir mapa",
      position_m: [1.2, 2.4],
      path_length_m: 3.1,
      risk: 0.22,
      information_gain: 0.84,
    }],
  });
  assert.equal(event.navigationRevision, 12);
  assert.deepEqual(event.candidates[0], {
    type: "FRONTIER",
    id: "FR-021",
    label: "Camino A",
    purpose: "Expandir mapa",
    x: 1.2,
    y: 2.4,
    pathLengthM: 3.1,
    risk: 0.22,
    informationGain: 0.84,
    frontierCells: null,
  });
});

test("unwraps a rosbridge std_msgs String frame", () => {
  const payload = {
    model_id: "YOLO11n-POSE",
    status: "LIVE",
    provider: "CUDAExecutionProvider",
    detection_count: 2,
    inference_latency_ms: 44,
    semantic_revision: 7,
  };
  const event = parseRosbridgeFrame(JSON.stringify({
    op: "publish",
    topic: "/pulso/hil/perception_telemetry",
    msg: { data: JSON.stringify(payload) },
  }));
  assert.equal(event.kind, "perception-telemetry");
  assert.equal(event.provider, "CUDAExecutionProvider");
  assert.equal(event.count, 2);
  assert.equal(event.latencyMs, 44);
  assert.equal(event.revision, 7);
});

test("rejects brain telemetry without a public summary", () => {
  assert.equal(parseBrainTrace({ category: "DECISION", hidden_reasoning: "secret" }), null);
  const event = parseBrainTrace({
    turn_id: "T-9",
    selected_world_seq: 22,
    category: "TOOL_REQUEST",
    label: "DECISIÓN",
    summary: "move_to(FR-021)",
    latency_ms: 810,
  });
  assert.equal(event.summary, "move_to(FR-021)");
  assert.equal(event.latencyMs, 810);
  assert.equal(event.worldSeq, 22);
});

test("perception telemetry remains tolerant to optional timing fields", () => {
  assert.deepEqual(parsePerceptionTelemetry({ model_id: "YOLO11n-POSE", status: "warming" }), {
    kind: "perception-telemetry",
    modelId: "YOLO11n-POSE",
    provider: null,
    status: "WARMING",
    count: null,
    latencyMs: null,
    frameAgeMs: null,
    revision: null,
    capturedNs: null,
  });
});

test("recognizes a bounded load_skill result without exposing hidden instructions", () => {
  const event = parseBrainTrace({
    turn_id: "T-10",
    category: "TOOL_RESULT",
    label: "load_skill",
    summary: "SKILL_LOADED",
    attributes: { skill_id: "vio_recovery", status: "SKILL_LOADED" },
  });
  assert.equal(event.skillId, "vio_recovery");
  assert.equal(event.skillState, "loaded");
});

test("reads the public cognitive brief from CONTEXT attributes", () => {
  const event = parseBrainTrace({
    turn_id: "T-11",
    selected_world_seq: 23,
    category: "CONTEXT",
    label: "COGNITIVE BRIEF",
    summary: "Contexto selectivo preparado para decidir.",
    attributes: {
      candidate_count: "3",
      decision_need: "CHOOSE_ROUTE",
      goal_id: "G-SEARCH-01",
      checkpoint: "M-001 / SECTOR NORTE",
      question: "¿A o B ofrece evidencia útil con riesgo aceptable?",
      plan_summary: "Comparar rutas y solicitar una vista si la evidencia es ambigua.",
      active_skill_id: "survivor_inspection",
    },
  });
  assert.equal(event.goal, "G-SEARCH-01");
  assert.equal(event.checkpoint, "M-001 / SECTOR NORTE");
  assert.equal(event.question, "¿A o B ofrece evidencia útil con riesgo aceptable?");
  assert.equal(event.decisionNeed, "CHOOSE_ROUTE");
  assert.equal(event.planSummary, "Comparar rutas y solicitar una vista si la evidencia es ambigua.");
  assert.equal(event.activeSkillId, "survivor_inspection");
});

test("store distinguishes deterministic alternatives from Gemma decisions", () => {
  const store = createMissionStore();
  store.ingest({
    kind: "candidates",
    navigationRevision: 4,
    candidates: [{ id: "FR-1" }, { id: "FR-2" }],
  }, 10);
  assert.equal(store.get().trace[0].source, "PLANIFICADOR DETERMINISTA");
  assert.equal(store.get().brain.connected, false);
});

test("fresh observation ids update live state without flooding the cognitive trace", () => {
  const store = createMissionStore();
  const observation = {
    kind: "observation",
    source: "GAZEBO_HIL",
    tracking: { state: "TRACKING", quality: 0.96, epoch: 1 },
    robot: {
      x: 0,
      y: 0,
      motionState: "STOPPED",
      frontRangeM: 1.4,
      bumperPressed: false,
      flashlightOn: false,
    },
  };
  store.ingest({ ...observation, observationId: "OBS-1" }, 1);
  store.ingest({ ...observation, observationId: "OBS-2", robot: { ...observation.robot, x: 0.08 } }, 2);
  store.ingest({
    kind: "brain-trace",
    turnId: "T-1",
    category: "DECISION",
    label: "DECISIÓN",
    summary: "Inspeccionar Camino A.",
    latencyMs: 900,
  }, 3);
  for (let index = 3; index <= 20; index += 1) {
    store.ingest({
      ...observation,
      observationId: `OBS-${index}`,
      robot: { ...observation.robot, x: index / 100 },
    }, index);
  }

  assert.equal(store.get().observation.observationId, "OBS-20");
  assert.equal(store.get().trace.filter((item) => item.source === "ROS / WORLDSTATE").length, 1);
  assert.equal(store.get().trace.some((item) => item.source === "GEMMA / ADK"), true);
});

test("safety, tracking, and motion transitions remain visible in the trace", () => {
  const store = createMissionStore();
  const base = {
    kind: "observation",
    source: "GAZEBO_HIL",
    tracking: { state: "TRACKING", quality: 0.96, epoch: 1 },
    robot: {
      x: 0,
      y: 0,
      motionState: "STOPPED",
      frontRangeM: 1.4,
      bumperPressed: false,
      flashlightOn: false,
    },
  };
  store.ingest({ ...base, observationId: "OBS-1" }, 1);
  store.ingest({
    ...base,
    observationId: "OBS-2",
    robot: { ...base.robot, motionState: "MOVING" },
  }, 2);
  store.ingest({
    ...base,
    observationId: "OBS-3",
    tracking: { ...base.tracking, state: "LIMITED" },
    robot: { ...base.robot, motionState: "MOVING", bumperPressed: true },
  }, 3);

  assert.equal(store.get().trace.filter((item) => item.source === "ROS / WORLDSTATE").length, 3);
});

test("a CONTEXT snapshot updates the cognitive brief and active skill", () => {
  const store = createMissionStore();
  const event = parseBrainTrace({
    turn_id: "T-12",
    category: "CONTEXT",
    label: "COGNITIVE BRIEF",
    summary: "Brief listo.",
    attributes: {
      goal_id: "G-SEARCH-01",
      checkpoint: "M-001",
      question: "¿Cuál ruta inspeccionar?",
      decision_need: "CHOOSE_ROUTE",
      plan_summary: "Inspeccionar evidencia antes de moverse.",
      active_skill_id: "survivor_inspection",
    },
  });
  store.ingest(event, 15);
  assert.equal(store.get().brain.goal, "G-SEARCH-01");
  assert.equal(store.get().brain.activeSkillId, "survivor_inspection");
  assert.equal(store.get().skills.find((skill) => skill.id === "survivor_inspection").state, "active");
});

test("an active skill reported by the phone is visible even outside the local catalog", () => {
  const store = createMissionStore();
  const event = parseBrainTrace({
    turn_id: "T-13",
    category: "CONTEXT",
    label: "COGNITIVE BRIEF",
    summary: "Skill de misión activa.",
    attributes: { active_skill_id: "debris_audio_probe" },
  });
  store.ingest(event, 17);
  assert.deepEqual(store.get().skills.at(-1), {
    id: "debris_audio_probe",
    description: "Skill reportada por el teléfono",
    state: "active",
  });
});

test("a real action result marks only its reported route as selected", () => {
  const store = createMissionStore();
  const result = parseActionResult({
    action_id: "A-17",
    accepted: true,
    status: "ACTIVE",
    detail: "MOVE_TO accepted",
    data: { target_id: "FR-021" },
  });
  store.ingest(result, 20);
  assert.deepEqual(store.get().selectedRoute, {
    targetId: "FR-021",
    actionId: "A-17",
    status: "ACTIVE",
  });
});

test("bridge URL defaults to the page host and supports explicit override", () => {
  assert.equal(resolveBridgeUrl({ protocol: "http:", hostname: "192.168.1.20", search: "" }), "ws://192.168.1.20:9091");
  assert.equal(
    resolveBridgeUrl({ protocol: "http:", hostname: "localhost", search: "?bridge=ws%3A%2F%2F10.0.0.8%3A9091" }),
    "ws://10.0.0.8:9091",
  );
});

test("normalizes the evidence-only interactive MetaView scene", () => {
  const event = parseMetaviewScene({
    contract_version: "pulso.metaview-scene.v1",
    captured_monotonic_ns: 91,
    frame_id: "map",
    sensor_map_seq: 12,
    navigation_revision: 4,
    map: {
      resolution_m: 0.05,
      origin_m: [-1, -2],
      width: 40,
      height: 30,
      known_cells: 123,
      unknown_cells: 1077,
      free_points_m: [[0, 0], [0.05, 0]],
      occupied_points_m: [[1, 1]],
    },
    robot: { position_m: [0.2, 0.3, 0], heading_deg: 45 },
    depth: { source: "/pulso/phone/depth/points", frame_id: "map", points_m: [[1, 0, 0.4]], sample_count: 1 },
    scan_footprint_m: [[0.2, 0.3, 0.02], [1, 0.5, 0.02]],
    routes: [{ id: "F_A", type: "FRONTIER", label: "A", selected: true, position_m: [1, 1, 0], path_m: [[0.2, 0.3, 0], [1, 1, 0]] }],
    bounds_m: [-1, -2, 2, 2],
  });
  assert.equal(event.kind, "metaview-scene");
  assert.equal(event.map.knownCells, 123);
  assert.deepEqual(event.depth.points, [[1, 0, 0.4]]);
  assert.equal(event.routes[0].selected, true);
  assert.deepEqual(event.routes[0].path.at(-1), [1, 1, 0]);
});

test("audits the exact turn-scoped Gemma input without exposing chain of thought", () => {
  const event = parseGemmaInput({
    input_id: "IN-1",
    turn_id: "TURN-1",
    selected_world_seq: 31,
    model_id: "gemma-4-E4B-it",
    backend: "LITERT_LM_PYTHON",
    input_kind: "MULTIMODAL",
    exact_message: { role: "user", parts: [{ text: "WORLD 31" }, { image: "ros:///audit" }] },
    system_prompt: "Use typed tools.",
    system_prompt_sha256: "abc",
    tool_schemas: [{ name: "move_to" }],
    tool_schemas_sha256: "def",
    context_tokens_before: 811,
    conversation_scope: "TURN",
    conversation_reused_across_turns: false,
    image: {
      kind: "TARGET_VIEW",
      source_topic: "/pulso/phone/rgb/compressed",
      format: "jpeg",
      jpeg_sha256: "1234",
      byte_length: 4096,
      audit_topic: "/pulso/hil/gemma_view/compressed",
    },
  });
  assert.equal(event.inputKind, "MULTIMODAL");
  assert.equal(event.conversationScope, "TURN");
  assert.equal(event.conversationReusedAcrossTurns, false);
  assert.equal(event.image.sha256, "1234");
  assert.equal("hidden_reasoning" in event, false);
});

test("a new Gemma turn clears the prior audit image until the exact payload arrives", () => {
  const store = createMissionStore();
  store.ingest({ kind: "gemma-view-image", base64: "old", format: "jpeg" }, 1);
  store.ingest({
    kind: "gemma-input",
    inputId: "IN-2",
    turnId: "TURN-2",
    worldSeq: 2,
    modelId: "gemma-4-E4B-it",
    inputKind: "MULTIMODAL",
    contextTokensBefore: 90,
    image: { kind: "TARGET_VIEW" },
  }, 2);
  assert.equal(store.get().images.gemmaView, null);
  store.ingest({ kind: "gemma-view-image", base64: "new", format: "jpeg" }, 3);
  assert.equal(store.get().images.gemmaView.base64, "new");
});

test("the spatial camera projects its target into the center", () => {
  const cameraState = { target: [1, 2, 0], yaw: 0, pitch: Math.PI / 3, distance: 5 };
  const camera = buildCamera(cameraState, 800, 600);
  const projected = projectPoint(cameraState.target, camera);
  assert.ok(projected);
  assert.ok(Math.abs(projected.x - 400) < 1e-9);
  assert.ok(Math.abs(projected.y - 300) < 1e-9);
});
