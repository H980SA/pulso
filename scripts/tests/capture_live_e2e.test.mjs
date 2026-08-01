import test from "node:test";
import assert from "node:assert/strict";

import {
  beginMoveMeasurement,
  bindSettledMoveMeasurements,
  createEvidence,
  distanceM,
  evaluateEvidence,
  markNextMotionBoundary,
  sha256,
  stableJson,
  summarizeScene,
} from "../capture_live_e2e.mjs";

test("stableJson ordena recursivamente las claves para el hash del runtime", () => {
  assert.equal(stableJson([{ b: 2, a: { d: 4, c: 3 } }]), '[{"a":{"c":3,"d":4},"b":2}]');
});

test("distanceM mide desplazamiento VIO en el plano", () => {
  assert.equal(distanceM({ x: 1, y: 2 }, { x: 1.3, y: 2.4 }), 0.5);
});

test("summarizeScene conserva solo evidencia espacial auditable", () => {
  assert.deepEqual(summarizeScene({
    captured_monotonic_ns: 3,
    sensor_map_seq: 4,
    navigation_revision: 5,
    map: { known_cells: 9, free_points_m: [[0, 0]], occupied_points_m: [[1, 1]] },
    depth: { sample_count: 7 },
    scan_footprint_m: [[0, 0, 0]],
    routes: [{ id: "F-1", selected: true }],
    robot: { position_m: [0, 0, 0] },
  }), {
    captured_monotonic_ns: 3,
    sensor_map_seq: 4,
    navigation_revision: 5,
    known_cells: 9,
    free_point_count: 1,
    occupied_point_count: 1,
    depth_sample_count: 7,
    scan_footprint_points: 1,
    route_count: 1,
    route_ids: ["F-1"],
    selected_route_id: "F-1",
    robot: { position_m: [0, 0, 0] },
  });
});

test("evaluateEvidence exige toda la cadena no-mock", () => {
  const evidence = createEvidence("ws://test");
  const system = "system";
  const tools = [{ type: "function", function: { name: "move_to" } }];
  evidence.gemma_inputs.push({
    input_id: "GI-1", turn_id: "T-1", input_kind: "WORLD_PACKET",
    image: null, runtime_hashes_valid: true,
  });
  evidence.gemma_inputs.push({
    input_id: "GI-2", turn_id: "T-2", input_kind: "WORLD_PACKET",
    image: { jpeg_sha256: sha256(Buffer.from("jpeg")), byte_length: 4 },
    system_prompt: system, tool_schemas: tools, runtime_hashes_valid: true,
  });
  evidence.gemma_views.push({ matched_input_id: "GI-2", metadata_match: true });
  evidence.brain_trace.push(
    { turn_id: "T-1", category: "TOOL_REQUEST", label: "move_to" },
    { turn_id: "T-1", category: "CYCLE_COMPLETE", label: "done" },
    {
      turn_id: "T-1", category: "TOOL_RESULT", label: "request_view",
      attributes: { image_ready_next_turn: true },
    },
  );
  evidence.actions["BH-1"] = {
    intent: { kind: "MOVE_TO" }, statuses: ["ACTIVE", "SUCCEEDED"], displacement_m: 0.12,
    pose_before: { captured_monotonic_ns: 100, x: 0, y: 0, motion_state: "STOPPED" },
    pose_after: { captured_monotonic_ns: 220, x: 0.12, y: 0, motion_state: "STOPPED" },
    displacement_measurement: {
      method: "FIRST_STOPPED_OBSERVATION_AFTER_TERMINAL",
      status: "BOUND_STOPPED",
      terminal_captured_monotonic_ns: 200,
      settled_captured_monotonic_ns: 220,
    },
  };
  evidence.perception_telemetry.push({
    model_id: "yolo11n-pose-onnx", provider: "CUDAExecutionProvider", status: "LIVE",
  });
  evidence.metaview_scenes.push({ known_cells: 1, route_count: 1, depth_sample_count: 1 });
  assert.equal(evaluateEvidence(evidence).ok, true);
});

test("MOVE_TO se mide con el primer STOPPED posterior al terminal monotónico", () => {
  const evidence = createEvidence("ws://test");
  const action = {
    intent: { kind: "MOVE_TO" },
    statuses: ["ACTIVE", "SUCCEEDED"],
    pose_before: { captured_monotonic_ns: 100, x: 0, y: 0, motion_state: "STOPPED" },
  };
  evidence.actions["BH-1"] = action;
  evidence.observations.push(
    { captured_monotonic_ns: 190, x: 0.03, y: 0, motion_state: "MOVING" },
    { captured_monotonic_ns: 210, x: 0.08, y: 0, motion_state: "STOPPED" },
    { captured_monotonic_ns: 220, x: 0.50, y: 0, motion_state: "STOPPED" },
  );

  beginMoveMeasurement(
    action,
    { status: "SUCCEEDED", captured_monotonic_ns: 200 },
    evidence.observations[0],
  );
  bindSettledMoveMeasurements(evidence);

  assert.equal(action.pose_after.captured_monotonic_ns, 210);
  assert.equal(action.displacement_m, 0.08);
  assert.equal(action.displacement_measurement.status, "BOUND_STOPPED");
  assert.equal(action.terminal_pose_snapshot.motion_state, "MOVING");
});

test("un movimiento futuro invalida la medición pendiente en vez de inflarla", () => {
  const evidence = createEvidence("ws://test");
  const action = {
    intent: { kind: "MOVE_TO" },
    statuses: ["ACTIVE", "SUCCEEDED"],
    pose_before: { captured_monotonic_ns: 100, x: 0, y: 0, motion_state: "STOPPED" },
  };
  evidence.actions["BH-1"] = action;
  beginMoveMeasurement(action, { status: "SUCCEEDED", captured_monotonic_ns: 200 }, null);
  evidence.actions["BH-2"] = { intent: { kind: "MOVE_TO" }, statuses: ["ACTIVE"] };
  markNextMotionBoundary(evidence, "BH-2", { status: "ACTIVE", captured_monotonic_ns: 250 });
  evidence.observations.push({
    captured_monotonic_ns: 300, x: 1, y: 0, motion_state: "STOPPED",
  });
  bindSettledMoveMeasurements(evidence);

  assert.equal(action.displacement_m, undefined);
  assert.equal(action.pose_after, undefined);
  assert.equal(action.displacement_measurement.status, "SUPERSEDED_BY_NEXT_MOTION");
  assert.equal(evaluateEvidence(evidence).metrics.settled_move_measurements, 0);
});

test("evaluateEvidence rechaza displacement sin sello STOPPED", () => {
  const evidence = createEvidence("ws://test");
  evidence.actions["BH-1"] = {
    intent: { kind: "MOVE_TO" },
    statuses: ["ACTIVE", "SUCCEEDED"],
    displacement_m: 4,
    displacement_measurement: { status: "AWAITING_STOPPED" },
  };
  const result = evaluateEvidence(evidence);
  assert.equal(result.metrics.successful_move_actions, 1);
  assert.equal(result.metrics.settled_move_measurements, 0);
  assert.equal(result.metrics.maximum_move_displacement_m, 0);
  assert.match(result.failures.join(" "), /5 cm/);
});

test("evaluateEvidence nunca aprueba una traza parcial", () => {
  const result = evaluateEvidence(createEvidence("ws://test"));
  assert.equal(result.ok, false);
  assert.ok(result.failures.length >= 8);
});

test("un JPEG con hash o longitud distinta no cuenta como imagen consumida", () => {
  const evidence = createEvidence("ws://test");
  evidence.gemma_views.push({ matched_input_id: "GI-1", metadata_match: false });
  const result = evaluateEvidence(evidence);
  assert.equal(result.ok, false);
  assert.match(result.failures.join(" "), /JPEG auditado/);
});
