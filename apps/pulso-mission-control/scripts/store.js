const SKILLS = Object.freeze([
  ["survivor_inspection", "Inspección multimodal de posible sobreviviente"],
  ["darkness_recovery", "Recuperación visual en oscuridad o contraluz"],
  ["vio_recovery", "Relocalización cuando VIO se degrada"],
]);

export function createMissionStore({ mode = "LIVE" } = {}) {
  let state = initialState(mode);
  const listeners = new Set();

  const notify = () => listeners.forEach((listener) => listener(state));
  const update = (recipe) => {
    state = recipe(state);
    notify();
  };

  return {
    get: () => state,
    subscribe(listener) {
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
    setBridge(status, detail) {
      update((current) => ({ ...current, bridge: { status, detail } }));
    },
    setSession(session) {
      update((current) => ({ ...current, session }));
    },
    setMode(mode) {
      update((current) => ({ ...current, mode }));
    },
    setPersistence(status, detail = "") {
      update((current) => ({ ...current, persistence: { status, detail } }));
    },
    ingest(event, receivedAt = performance.now(), metadata = {}) {
      update((current) => appendEventLog(reduceEvent(current, event, receivedAt), event, receivedAt, metadata));
    },
  };
}

function initialState(mode) {
  return {
    mode,
    bridge: { status: "waiting", detail: "Sin conexión" },
    session: null,
    persistence: { status: "waiting", detail: "Esperando el primer evento real" },
    startedAt: performance.now(),
    observation: null,
    candidates: null,
    metaViewScene: null,
    actionResults: [],
    selectedRoute: null,
    tracks: null,
    phoneTelemetry: null,
    cameraInfo: null,
    brain: {
      connected: false,
      modelStatus: "WAITING",
      goal: null,
      checkpoint: null,
      question: null,
      decisionNeed: null,
      planSummary: null,
      activeSkillId: null,
      contextTokens: null,
      loopLatencyMs: null,
    },
    skills: SKILLS.map(([id, description]) => ({ id, description, state: "waiting" })),
    perception: {},
    gemmaInput: null,
    images: { metaView: null, camera: null, gemmaView: null },
    metrics: {
      mapIntervalMs: null,
      cameraIntervalMs: null,
      lastMapReceivedAt: null,
      lastCameraReceivedAt: null,
    },
    trace: [],
    events: [],
  };
}

function appendEventLog(state, event, receivedAt, metadata) {
  const sequence = metadata.seq ?? state.events.length + 1;
  const entry = {
    id: `${sequence}:${event.kind}:${receivedAt}`,
    sequence,
    topic: metadata.topic || "internal",
    kind: event.kind,
    receivedAt,
    capturedNs: event.capturedNs ?? null,
    event,
    artifactSha256: metadata.artifactSha256 || null,
    eventHash: metadata.eventHash || null,
  };
  return { ...state, events: [...state.events, entry].slice(-500) };
}

function reduceEvent(state, event, receivedAt) {
  if (event.kind === "observation") return ingestObservation(state, event, receivedAt);
  if (event.kind === "candidates") return ingestCandidates(state, event, receivedAt);
  if (event.kind === "metaview-scene") return { ...state, metaViewScene: event };
  if (event.kind === "action-result") return ingestActionResult(state, event, receivedAt);
  if (event.kind === "perception-tracks") return { ...state, tracks: event };
  if (event.kind === "brain-trace") return ingestBrainTrace(state, event, receivedAt);
  if (event.kind === "gemma-input") return ingestGemmaInput(state, event, receivedAt);
  if (event.kind === "perception-telemetry") return ingestPerception(state, event);
  if (event.kind === "phone-telemetry") return { ...state, phoneTelemetry: event };
  if (event.kind === "phone-camera-info") return { ...state, cameraInfo: event };
  if (event.kind === "metaview-image") return ingestImage(state, "metaView", event, receivedAt);
  if (event.kind === "camera-image") return ingestImage(state, "camera", event, receivedAt);
  if (event.kind === "gemma-view-image") return ingestImage(state, "gemmaView", event, receivedAt);
  return state;
}

function ingestGemmaInput(state, event, receivedAt) {
  const newTurn = state.gemmaInput?.turnId !== event.turnId;
  const trace = appendTrace(state.trace, {
    id: `gemma-input:${event.inputId}`,
    stage: "observe",
    label: "MODEL INPUT",
    source: "GEMMA / LITERT-LM",
    summary: `${event.inputKind} · world ${event.worldSeq ?? "—"} · ${event.image ? event.image.kind : "TEXT ONLY"}`,
    at: receivedAt,
  });
  return {
    ...state,
    gemmaInput: event,
    brain: {
      ...state.brain,
      connected: true,
      modelStatus: "LIVE",
      contextTokens: event.contextTokensBefore ?? state.brain.contextTokens,
    },
    images: newTurn
      ? { ...state.images, gemmaView: null }
      : state.images,
    trace,
  };
}

function ingestObservation(state, event, receivedAt) {
  const previous = state.observation;
  const trace = !isMaterialObservationChange(previous, event) ? state.trace : appendTrace(state.trace, {
    id: `obs:${event.observationId}`,
    stage: "observe",
    label: "OBSERVACIÓN",
    source: "ROS / WORLDSTATE",
    summary: `${event.tracking.state} · pose ${formatCoord(event.robot.x)}, ${formatCoord(event.robot.y)} · frente ${formatRange(event.robot.frontRangeM)}`,
    at: receivedAt,
  });
  return { ...state, observation: event, trace };
}

function isMaterialObservationChange(previous, current) {
  if (!previous) return true;
  return previous.source !== current.source
    || previous.tracking.state !== current.tracking.state
    || previous.tracking.epoch !== current.tracking.epoch
    || previous.robot.motionState !== current.robot.motionState
    || previous.robot.bumperPressed !== current.robot.bumperPressed
    || previous.robot.flashlightOn !== current.robot.flashlightOn;
}

function ingestCandidates(state, event, receivedAt) {
  const changed = state.candidates?.navigationRevision !== event.navigationRevision;
  const trace = !changed ? state.trace : appendTrace(state.trace, {
    id: `nav:${event.navigationRevision}`,
    stage: "compare",
    label: "ALTERNATIVAS",
    source: "PLANIFICADOR DETERMINISTA",
    summary: event.candidates.length
      ? `${event.candidates.length} rutas vigentes: ${event.candidates.map((item, index) => `${String.fromCharCode(65 + index)}=${item.id}`).join(" · ")}`
      : "No hay candidato transitable vigente.",
    at: receivedAt,
  });
  return { ...state, candidates: event, trace };
}

function ingestActionResult(state, event, receivedAt) {
  const targetId = typeof event.data.target_id === "string"
    ? event.data.target_id
    : typeof event.data.candidate_id === "string" ? event.data.candidate_id : null;
  const trace = appendTrace(state.trace, {
    id: `result:${event.actionId}:${event.status}`,
    stage: event.status === "ACTIVE" ? "act" : event.accepted ? "result" : "error",
    label: event.status === "ACTIVE" ? "ACCIÓN" : "RESULTADO",
    source: "GUARD / ROBOT",
    summary: `${event.actionId} · ${event.status} · ${event.detail}`,
    at: receivedAt,
  });
  return {
    ...state,
    actionResults: [...state.actionResults, event].slice(-20),
    selectedRoute: targetId
      ? { targetId, actionId: event.actionId, status: event.status }
      : state.selectedRoute,
    trace,
  };
}

function ingestBrainTrace(state, event, receivedAt) {
  const stage = brainStage(event.category);
  const loopFinished = ["RESPONSE", "MODEL_RESPONSE", "TURN_COMPLETE", "LOOP_COMPLETE", "CYCLE_COMPLETE"].includes(event.category);
  const isContextSnapshot = event.category === "CONTEXT";
  const activeSkillId = isContextSnapshot
    ? event.activeSkillId
    : event.activeSkillId || state.brain.activeSkillId;
  const brain = {
    ...state.brain,
    connected: true,
    modelStatus: event.category === "ERROR" ? "ERROR" : "LIVE",
    goal: event.goal || state.brain.goal,
    checkpoint: event.checkpoint || state.brain.checkpoint,
    question: event.question || state.brain.question,
    decisionNeed: event.decisionNeed || state.brain.decisionNeed,
    planSummary: event.planSummary || state.brain.planSummary,
    activeSkillId,
    contextTokens: event.contextTokens ?? state.brain.contextTokens,
    loopLatencyMs: loopFinished && event.latencyMs !== null
      ? event.latencyMs
      : state.brain.loopLatencyMs,
  };
  let skills = state.skills.map((skill) => {
    let skillState = skill.state;
    if (event.skillId === skill.id) skillState = normalizeSkillState(event.skillState);
    if (isContextSnapshot && skillState === "active") skillState = "loaded";
    if (activeSkillId === skill.id) skillState = "active";
    return skillState === skill.state ? skill : { ...skill, state: skillState };
  });
  const reportedSkillId = activeSkillId || event.skillId;
  if (reportedSkillId && !skills.some((skill) => skill.id === reportedSkillId)) {
    skills = [...skills, {
      id: reportedSkillId,
      description: "Skill reportada por el teléfono",
      state: activeSkillId === reportedSkillId ? "active" : normalizeSkillState(event.skillState),
    }];
  }
  const trace = appendTrace(state.trace, {
    id: `brain:${event.turnId}:${event.category}:${receivedAt}`,
    stage,
    label: event.label,
    source: "GEMMA / ADK",
    summary: event.summary,
    latencyMs: event.latencyMs,
    at: receivedAt,
  });
  return { ...state, brain, skills, trace };
}

function ingestPerception(state, event) {
  return {
    ...state,
    perception: { ...state.perception, [event.modelId]: event },
  };
}

function ingestImage(state, key, event, receivedAt) {
  if (key === "gemmaView") {
    return { ...state, images: { ...state.images, gemmaView: event } };
  }
  const timestampKey = key === "metaView" ? "lastMapReceivedAt" : "lastCameraReceivedAt";
  const intervalKey = key === "metaView" ? "mapIntervalMs" : "cameraIntervalMs";
  const previousAt = state.metrics[timestampKey];
  return {
    ...state,
    images: { ...state.images, [key]: event },
    metrics: {
      ...state.metrics,
      [timestampKey]: receivedAt,
      [intervalKey]: previousAt === null ? null : receivedAt - previousAt,
    },
  };
}

function appendTrace(trace, event) {
  if (trace.some((item) => item.id === event.id)) return trace;
  return [...trace, event].slice(-10);
}

function brainStage(category) {
  const normalized = category.toUpperCase();
  if (["CONTEXT", "PACKET", "OBSERVE", "OBSERVATION"].includes(normalized)) return "observe";
  if (["CANDIDATES", "ALTERNATIVES", "COMPARE"].includes(normalized)) return "compare";
  if (["TOOL", "TOOL_REQUEST", "DECISION", "RESPONSE", "MODEL_RESPONSE"].includes(normalized)) return "decide";
  if (["ACTION", "DISPATCH"].includes(normalized)) return "act";
  if (["RESULT", "TOOL_RESULT", "CYCLE_COMPLETE", "TURN_COMPLETE", "LOOP_COMPLETE"].includes(normalized)) return "result";
  if (normalized === "ERROR") return "error";
  return "decide";
}

function normalizeSkillState(state) {
  const normalized = String(state || "loaded").toLowerCase();
  return ["active", "loaded", "evicted", "waiting"].includes(normalized) ? normalized : "loaded";
}

function formatCoord(value) {
  return value === null ? "—" : value.toFixed(2);
}

function formatRange(value) {
  return value === null ? "sin lectura" : `${value.toFixed(2)}m`;
}
