const ROUTE_COLORS = ["#ff4b20", "#df41ae", "#1aa9bf", "#209447", "#f2a900", "#6c5bd4"];
const IMAGE_KINDS = new Set(["camera-image", "metaview-image", "gemma-view-image"]);

export function createRenderer({ tacticalMap, spatialMap, cameraView, bridgeUrl }) {
  const el = bindElements();
  let lastMetaFrame = null;
  let lastCameraFrame = null;
  let lastGemmaFrame = null;
  let lastSceneKey = null;
  let selectedEventId = null;
  let timelineFilter = "all";
  let selectedRouteId = null;
  let sessions = [];
  let selectedSessionId = null;
  let latestState = null;

  const render = (state) => {
    latestState = state;
    renderStatus(el, state, bridgeUrl);
    renderMission(el, state);
    renderTimeline(el, state, selectedEventId, timelineFilter);
    renderMap(el, state, selectedRouteId);
    renderSensors(el, state);
    renderSessionFooter(el, state);
    renderSessions(el, sessions, selectedSessionId);
    const heading = state.observation?.robot?.headingDeg;
    tacticalMap.setHeading(heading ?? 0);
    if (state.images.metaView?.base64 && state.images.metaView.base64 !== lastMetaFrame) {
      lastMetaFrame = state.images.metaView.base64;
      tacticalMap.setFrame(lastMetaFrame, state.images.metaView.format);
    }
    if (state.images.camera?.base64 && state.images.camera.base64 !== lastCameraFrame) {
      lastCameraFrame = state.images.camera.base64;
      cameraView.setFrame(lastCameraFrame, state.images.camera.format);
    }
    cameraView.setTracks(state.tracks?.tracks || []);
    const scene = state.metaViewScene;
    const sceneKey = scene ? `${scene.capturedNs}:${scene.navigationRevision}` : null;
    if (scene && sceneKey !== lastSceneKey) {
      lastSceneKey = sceneKey;
      spatialMap.setScene(scene);
    }
    if (state.images.gemmaView?.base64) lastGemmaFrame = state.images.gemmaView.base64;
  };

  render.selectEvent = (id) => { selectedEventId = id; if (latestState) renderTimeline(el, latestState, id, timelineFilter); };
  render.setTimelineFilter = (filter) => {
    timelineFilter = filter === "gemma" ? "gemma" : "all";
    selectedEventId = null;
    if (latestState) renderTimeline(el, latestState, selectedEventId, timelineFilter);
  };
  render.selectRoute = (id) => { selectedRouteId = id; if (latestState) renderMap(el, latestState, id); };
  render.setSessions = (value) => { sessions = value; renderSessions(el, sessions, selectedSessionId); };
  render.selectSession = (id) => { selectedSessionId = id; renderSessions(el, sessions, id); };
  render.selectedSession = () => sessions.find((item) => item.session_id === selectedSessionId) || null;
  render.lastFrames = () => ({ lastMetaFrame, lastCameraFrame, lastGemmaFrame });
  return render;
}

function bindElements() {
  const byId = (id) => document.getElementById(id);
  const ids = [
    "bridge-status", "model-status", "save-status", "connection-toggle", "mission-id", "flow-goal",
    "flow-checkpoint", "flow-question", "flow-need", "flow-plan", "mission-event-list", "active-goal",
    "mission-description", "mission-success", "mission-evidence-list", "mission-evidence-image",
    "mission-evidence-empty", "mission-evidence-caption", "active-question", "checkpoint-status", "skill-list",
    "source-status", "mission-state", "vio-status", "gemma-world", "map-sequence", "gemma-model",
    "session-integrity", "event-timeline", "event-kind", "event-title", "event-summary", "event-payload",
    "event-sequence", "gemma-turn", "event-topic", "event-captured", "event-hash", "model-latency",
    "detector-latency", "detail-gemma-image", "detail-gemma-empty", "detail-camera-image", "detail-camera-empty",
    "detail-map-image", "detail-map-empty", "detail-route-canvas", "route-count", "route-strip", "route-detail",
    "spatial-mode", "spatial-evidence", "spatial-depth", "map-live-stamp", "map-sequence-secondary",
    "nav-revision", "robot-pose", "map-latency", "detector-table-body", "camera-rate", "detection-count",
    "detection-list", "sensor-model", "sensor-provider", "sensor-latency", "sensor-confidence", "sensor-keypoints",
    "sensor-frame-time", "sessions-list", "session-title", "session-summary", "session-replay", "session-export",
    "session-event-preview", "session-id", "session-source", "session-started", "session-ended",
    "session-event-count", "session-hash", "current-session-id", "event-total", "mission-clock", "truth-label",
  ];
  return Object.fromEntries(ids.map((id) => [camel(id), byId(id)]));
}

function renderStatus(el, state, bridgeUrl) {
  const tone = state.mode === "REPLAY" ? "replay" : state.bridge.status;
  el.bridgeStatus.dataset.tone = tone;
  el.bridgeStatus.textContent = state.mode === "REPLAY" ? "REPLAY" : state.bridge.status.toUpperCase();
  el.bridgeStatus.title = `${state.bridge.detail} · ${bridgeUrl}`;
  el.modelStatus.textContent = state.mode === "REPLAY" ? "REPLAY" : state.brain.modelStatus;
  el.modelStatus.dataset.tone = state.mode === "REPLAY"
    ? "replay" : state.brain.modelStatus === "LIVE" ? "live" : state.brain.modelStatus === "ERROR" ? "error" : "waiting";
  el.connectionToggle.textContent = state.bridge.status === "live" ? "DESCONECTAR" : "CONECTAR";
  el.connectionToggle.disabled = state.mode !== "LIVE";
  el.sourceStatus.textContent = state.observation?.source || "SIN DATOS";
  el.vioStatus.textContent = state.observation ? `${state.observation.tracking.state} ${percent(state.observation.tracking.quality)}` : "—";
  el.missionState.textContent = state.observation ? "ACTIVO" : "WAITING";
  el.missionState.dataset.tone = state.observation ? "live" : "waiting";
}

function renderMission(el, state) {
  const brain = state.brain;
  el.flowGoal.textContent = brain.goal || "ESPERANDO CONTEXTO";
  el.flowCheckpoint.textContent = brain.checkpoint || "NO RECIBIDO";
  el.flowQuestion.textContent = brain.question || "NO RECIBIDA";
  el.flowNeed.textContent = brain.decisionNeed || "NO REPORTADA";
  el.flowPlan.textContent = brain.planSummary || "Esperando un resumen público del runtime.";
  el.activeGoal.textContent = brain.goal || "—";
  el.activeQuestion.textContent = brain.question || "NO RECIBIDA";
  el.checkpointStatus.textContent = brain.checkpoint || "NO RECIBIDO";
  el.missionSuccess.textContent = brain.decisionNeed
    ? `Resolver ${brain.decisionNeed} mediante una acción y resultado verificables.`
    : "Esperando condición verificable.";
  el.missionDescription.textContent = brain.planSummary || "La misión se completa únicamente con evidencia recibida por ROS.";
  const recent = state.events.filter((item) => !IMAGE_KINDS.has(item.kind)).slice(-7);
  el.missionEventList.replaceChildren(...recent.map((item) => {
    const row = node("li");
    row.append(node("time", "", clock(item.receivedAt)), node("span", "", eventTitle(item)));
    return row;
  }));
  const evidence = state.events.filter((item) => IMAGE_KINDS.has(item.kind) || item.kind === "action-result" || item.kind === "perception-tracks").slice(-4);
  el.missionEvidenceList.replaceChildren(...(evidence.length ? evidence.map((item) => {
    const row = node("li");
    row.append(node("strong", "", eventTitle(item)), node("span", "", "VERIFICADO / RECIBIDO"));
    return row;
  }) : [node("li", "", "Sin evidencia recibida.")]));
  renderSkills(el.skillList, state.skills);
  const latestImage = state.images.gemmaView || state.images.camera || state.images.metaView;
  setImage(el.missionEvidenceImage, el.missionEvidenceEmpty, latestImage);
  el.missionEvidenceCaption.textContent = latestImage ? `${latestImage.kind} · ${latestImage.capturedNs ?? "sin timestamp"}` : "Sin evidencia visual.";
  el.gemmaWorld.textContent = state.gemmaInput?.worldSeq ?? "—";
  el.mapSequence.textContent = state.candidates?.sensorMapSeq ?? state.metaViewScene?.mapSeq ?? "—";
  el.gemmaModel.textContent = state.gemmaInput?.modelId || "—";
  el.sessionIntegrity.textContent = shortHash(state.session?.integrity_hash);
}

function renderTimeline(el, state, selectedId, filter = "all") {
  const visibleEvents = state.events.filter((item) => filter !== "gemma" || isGemmaEvent(item));
  const selected = visibleEvents.find((item) => item.id === selectedId) || visibleEvents.at(-1) || null;
  el.eventTimeline.replaceChildren(...(visibleEvents.length ? visibleEvents.slice(-120).map((item) => {
    const row = node("li");
    const button = node("button", "event-row");
    button.type = "button"; button.dataset.eventId = item.id; button.dataset.kind = item.kind;
    button.setAttribute("aria-current", String(selected?.id === item.id));
    const copy = node("span", "event-copy");
    copy.append(node("strong", "", eventTitle(item)), node("span", "", eventSummary(item)));
    button.append(node("time", "", `+${seconds(item.receivedAt)}s`), node("span", "event-icon", eventIcon(item.kind)), copy);
    row.append(button); return row;
  }) : [node("li", "", filter === "gemma" ? "Esperando una entrada o evento real de Gemma." : "Esperando eventos ROS.")]));
  if (!selected) {
    el.eventKind.textContent = "WAITING";
    el.eventTitle.textContent = filter === "gemma" ? "SOLO GEMMA" : "Selecciona un evento";
    el.eventSummary.textContent = "No hay datos reales para mostrar todavía.";
    el.eventPayload.textContent = "Sin payload recibido.";
    setImage(el.detailGemmaImage, el.detailGemmaEmpty, null);
    setImage(el.detailCameraImage, el.detailCameraEmpty, null);
    setImage(el.detailMapImage, el.detailMapEmpty, null);
    return;
  }
  el.eventKind.textContent = selected.kind.toUpperCase();
  el.eventTitle.textContent = eventTitle(selected);
  el.eventSummary.textContent = eventSummary(selected);
  el.eventPayload.textContent = operatorEventDetail(selected);
  el.eventSequence.textContent = selected.sequence;
  el.gemmaTurn.textContent = selected.event.turnId || state.gemmaInput?.turnId || "—";
  el.eventTopic.textContent = selected.topic;
  el.eventCaptured.textContent = selected.capturedNs ?? "—";
  el.eventHash.textContent = selected.eventHash || "LIVE / PENDIENTE";
  el.modelLatency.textContent = ms(state.brain.loopLatencyMs);
  const detectorTimes = Object.values(state.perception).map((item) => item.latencyMs).filter(Number.isFinite);
  el.detectorLatency.textContent = detectorTimes.length ? ms(Math.min(...detectorTimes)) : "—";
  const turnInput = inputForEvent(state.events, selected);
  setImage(el.detailGemmaImage, el.detailGemmaEmpty, exactImageFor(state.events, selected, "gemma-view-image", turnInput?.event.image?.capturedNs));
  setImage(el.detailCameraImage, el.detailCameraEmpty, exactImageFor(state.events, selected, "camera-image", selected.capturedNs));
  setImage(el.detailMapImage, el.detailMapEmpty, exactImageFor(state.events, selected, "metaview-image", selected.capturedNs));
  drawRouteEvidence(el.detailRouteCanvas, selected.kind === "metaview-scene" ? selected.event : null);
}

function isGemmaEvent(item) {
  if (item.kind === "gemma-input" || item.kind === "gemma-view-image") return true;
  if (item.kind !== "brain-trace") return false;
  return new Set([
    "CONTEXT", "TOOL_REQUEST", "TOOL_RESULT", "MODEL_RESPONSE",
    "CYCLE_COMPLETE", "CANCELED", "ERROR",
  ]).has(item.event.category);
}

function inputForEvent(events, selected) {
  if (selected.kind === "gemma-input") return selected;
  const turnId = selected.event.turnId;
  if (!turnId) return null;
  return [...events].reverse().find((item) => item.kind === "gemma-input" && item.event.turnId === turnId) || null;
}

function exactImageFor(events, selected, kind, capturedNs) {
  if (selected.kind === kind) return selected.event;
  if (!Number.isFinite(capturedNs)) return null;
  return [...events].reverse().find((item) => item.kind === kind && item.capturedNs === capturedNs)?.event || null;
}

function operatorEventDetail(item) {
  const event = item.event;
  if (item.kind === "gemma-input") {
    const tools = event.toolSchemas.length
      ? event.toolSchemas.map((tool) => `- ${tool.name || "tool"}: ${tool.description || "sin descripción"}`).join("\n")
      : "- Sin tools declaradas";
    const message = event.promptText || safeJson(event.exactMessage) || "Sin mensaje";
    const image = event.image
      ? `${event.image.kind || "imagen"} · ${event.image.byteLength ?? "—"} bytes · sha256 ${event.image.sha256 || "—"}`
      : "Sin imagen en este turno";
    return [
      "ENTRADA EXACTA A GEMMA",
      `turn_id: ${event.turnId}`,
      `modelo: ${event.modelId} · backend: ${event.backend || "—"}`,
      `world_seq: ${event.worldSeq ?? "—"} · scope: ${event.conversationScope || "—"}`,
      "",
      "MENSAJE DE TURNO",
      message,
      "",
      "SYSTEM PROMPT",
      event.systemPrompt || "No publicado",
      "",
      "TOOLS DISPONIBLES",
      tools,
      "",
      "IMAGEN MULTIMODAL",
      image,
    ].join("\n");
  }
  if (item.kind === "brain-trace") {
    const headings = {
      CONTEXT: "CONTEXTO SELECCIONADO PARA GEMMA",
      TOOL_REQUEST: "GEMMA SOLICITÓ UNA TOOL",
      TOOL_RESULT: "RESULTADO DEVUELTO A GEMMA",
      MODEL_RESPONSE: "RESPUESTA PÚBLICA DE GEMMA",
      CYCLE_COMPLETE: "CICLO DE GEMMA COMPLETADO",
      CANCELED: "TURNO DE GEMMA CANCELADO",
      ERROR: "ERROR DEL RUNTIME DE GEMMA",
    };
    return [
      headings[event.category] || event.category,
      event.summary,
      "",
      `turn_id: ${event.turnId}`,
      `world_seq: ${event.worldSeq ?? "—"}`,
      `latencia: ${Number.isFinite(event.latencyMs) ? `${event.latencyMs} ms` : "—"}`,
      "",
      "PROPIEDADES PÚBLICAS EXACTAS",
      safeJson(event.attributes || {}),
      "",
      "Nota: se muestra la explicación pública y los eventos observables; no cadena de pensamiento privada.",
    ].join("\n");
  }
  return safeJson(event);
}

function renderMap(el, state, selectedId) {
  const candidates = state.candidates?.candidates || [];
  const selected = candidates.find((item) => item.id === selectedId)
    || candidates.find((item) => item.id === state.selectedRoute?.targetId) || candidates[0] || null;
  el.routeCount.textContent = `${candidates.length} rutas`;
  el.routeStrip.replaceChildren(...(candidates.length ? candidates.slice(0, 6).map((candidate, index) => {
    const row = node("li"); const button = node("button", "route-row");
    button.type = "button"; button.dataset.candidateId = candidate.id;
    button.setAttribute("aria-current", String(selected?.id === candidate.id));
    const copy = node("span", "route-copy");
    copy.append(node("strong", "", `${candidate.type} · ${candidate.id}`), node("span", "", candidate.label));
    const metric = node("span", "route-metric", `${meters(candidate.pathLengthM)}\n${percent(candidate.informationGain)} info`);
    button.append(node("span", "route-letter", String.fromCharCode(65 + index)), copy, metric); row.append(button); return row;
  }) : [node("li", "", "ESPERANDO CANDIDATOS")])) ;
  el.routeDetail.replaceChildren(...routeDetails(selected));
  const robot = state.observation?.robot;
  el.mapSequenceSecondary.textContent = state.candidates?.sensorMapSeq ?? state.metaViewScene?.mapSeq ?? "—";
  el.navRevision.textContent = state.candidates?.navigationRevision ?? state.metaViewScene?.navigationRevision ?? "—";
  el.robotPose.textContent = robot ? `${fixed(robot.x)}, ${fixed(robot.y)} · ${fixed(robot.headingDeg, 0)}°` : "—";
  el.mapLatency.textContent = ms(state.metrics.mapIntervalMs);
  const scene = state.metaViewScene;
  el.spatialMode.textContent = scene ? `3D / ${scene.frameId.toUpperCase()}` : "3D / WAITING";
  el.spatialEvidence.textContent = scene ? `${scene.map.knownCells ?? 0} CELDAS · ${scene.routes.length} RUTAS` : "SIN GEOMETRÍA";
  el.spatialDepth.textContent = scene ? `DEPTH ${scene.depth.points.length} PTS` : "DEPTH —";
  el.mapLiveStamp.textContent = state.metrics.lastMapReceivedAt === null ? "NO SIGNAL" : "LIVE";
}

function renderSensors(el, state) {
  const tracks = state.tracks?.tracks || [];
  const perception = Object.values(state.perception);
  const primary = perception.find((item) => item.modelId.toUpperCase().includes("YOLO")) || perception[0];
  const rows = [
    [primary?.modelId || "YOLO11n-POSE", primary ? `${primary.count ?? 0} · ${ms(primary.latencyMs)}` : "SIN TELEMETRÍA", primary?.status || "WAITING"],
    ["PHONE RGB", state.images.camera ? frameRate(state.metrics.cameraIntervalMs) : "SIN FRAME", state.images.camera ? "LIVE" : "WAITING"],
    ["ARCORE DEPTH", state.observation ? meters(state.observation.robot.frontRangeM) : "SIN ESTADO", state.observation ? "LIVE" : "WAITING"],
    ["VIO", state.observation?.tracking.state || "SIN ESTADO", state.observation ? "LIVE" : "WAITING"],
    ["PHONE IMU", state.phoneTelemetry?.accelerationMps2 ? vectorReading(state.phoneTelemetry.accelerationMps2, "m/s²") : "SIN MUESTRA", state.phoneTelemetry ? "LIVE" : "WAITING"],
    ["BATTERY", state.phoneTelemetry ? `${percent(state.phoneTelemetry.batteryFraction)} · ${temperature(state.phoneTelemetry.batteryTemperatureC)}` : "SIN TELEMETRÍA", state.phoneTelemetry ? "LIVE" : "WAITING"],
    ["RGB INTRINSICS", state.cameraInfo ? `${state.cameraInfo.width}×${state.cameraInfo.height} · fx ${fixed(state.cameraInfo.k[0], 0)}` : "SIN CALIBRACIÓN", state.cameraInfo ? "LIVE" : "WAITING"],
  ];
  el.detectorTableBody.replaceChildren(...rows.map(([source, reading, status]) => {
    const row = node("tr"); const stateCell = node("td", "", status); stateCell.dataset.tone = status.toLowerCase();
    row.append(node("td", "", source), node("td", "", reading), stateCell); return row;
  }));
  el.cameraRate.textContent = state.images.camera ? `${frameRate(state.metrics.cameraIntervalMs)} FPS` : "— FPS";
  el.detectionCount.textContent = `${tracks.length} TRACK${tracks.length === 1 ? "" : "S"}`;
  el.detectionList.replaceChildren(...(tracks.length ? tracks.map((track) => {
    const row = node("li"); row.append(node("span", "", track.id), node("span", "", `${track.label} · ${track.modelId || "modelo"}`), node("span", "", percent(track.confidence))); return row;
  }) : [node("li", "", "Sin detecciones reportadas.")]));
  const track = tracks[0];
  el.sensorModel.textContent = primary?.modelId || track?.modelId || "YOLO11n-POSE";
  el.sensorProvider.textContent = primary?.provider || "—";
  el.sensorLatency.textContent = ms(primary?.latencyMs ?? track?.inferenceLatencyMs);
  el.sensorConfidence.textContent = percent(track?.confidence);
  el.sensorKeypoints.textContent = track?.visibleKeypoints ?? "—";
  el.sensorFrameTime.textContent = state.images.camera?.capturedNs ?? "—";
}

function vectorReading(vector, unit) {
  return `${vector.map((value) => fixed(value, 2)).join(", ")} ${unit}`;
}

function temperature(value) {
  return Number.isFinite(value) ? `${fixed(value, 1)} °C` : "temp —";
}

function renderSessionFooter(el, state) {
  const persistence = state.persistence?.status || "waiting";
  el.saveStatus.textContent = persistence === "error" ? "ERROR" : persistence === "saving" ? "GUARDANDO" : state.session?.session_id ? "GUARDADO" : state.mode === "LIVE" ? "SIN DATOS" : state.mode;
  el.saveStatus.dataset.tone = persistence === "error" ? "error" : persistence === "saving" ? "saving" : state.session?.session_id ? "saved" : state.mode === "REPLAY" ? "replay" : "waiting";
  el.saveStatus.title = state.persistence?.detail || "";
  el.currentSessionId.textContent = state.session?.session_id || "SIN SESIÓN";
  el.eventTotal.textContent = `${state.events.length} eventos`;
  el.missionClock.textContent = clock(performance.now() - state.startedAt);
  el.truthLabel.textContent = state.mode === "LIVE" ? "LIVE muestra solo mensajes recibidos." : `${state.mode}: datos claramente separados de LIVE.`;
}

function renderSessions(el, sessions, selectedId) {
  const selected = sessions.find((item) => item.session_id === selectedId) || null;
  el.sessionsList.replaceChildren(...(sessions.length ? sessions.map((session) => {
    const row = node("li"); const button = node("button", "session-row"); button.type = "button";
    button.dataset.sessionId = session.session_id; button.setAttribute("aria-current", String(selected?.session_id === session.session_id));
    button.append(node("strong", "", session.session_id), node("span", "", `${session.started_at} · ${session.event_count} eventos`), node("b", "", session.ended_at ? "COMPLETA" : "ABIERTA")); row.append(button); return row;
  }) : [node("li", "", "No hay sesiones persistidas.")]));
  if (!selected) return;
  el.sessionTitle.textContent = selected.session_id;
  el.sessionSummary.textContent = `${selected.source} · ${selected.event_count} eventos · hash encadenado`;
  el.sessionReplay.disabled = selected.event_count === 0;
  el.sessionExport.href = `/api/sessions/${encodeURIComponent(selected.session_id)}/export`;
  el.sessionExport.setAttribute("aria-disabled", String(selected.event_count === 0));
  el.sessionId.textContent = selected.session_id; el.sessionSource.textContent = selected.source;
  el.sessionStarted.textContent = selected.started_at; el.sessionEnded.textContent = selected.ended_at || "ABIERTA";
  el.sessionEventCount.textContent = selected.event_count; el.sessionHash.textContent = selected.integrity_hash || "—";
  const preview = node("li");
  preview.append(
    node("span", "", "✓"),
    node("span", "", `${selected.event_count} eventos disponibles para replay verificable.`),
  );
  el.sessionEventPreview.replaceChildren(preview);
}

function renderSkills(container, skills) {
  container.replaceChildren(...skills.map((skill) => { const row = node("li"); row.append(node("span", "", skill.id), node("span", "", skill.state.toUpperCase())); row.lastElementChild.dataset.skillState = skill.state; return row; }));
}

function routeDetails(candidate) {
  if (!candidate) return [detailRow("estado", "ESPERANDO CANDIDATOS")];
  return [detailRow("tipo", candidate.type), detailRow("objetivo", candidate.id), detailRow("longitud", meters(candidate.pathLengthM)), detailRow("riesgo", percent(candidate.risk)), detailRow("ganancia de información", percent(candidate.informationGain)), detailRow("estado", "ELEGIBLE / RECIBIDA")];
}
function detailRow(label, value) { const row = node("div"); row.append(node("dt", "", label), node("dd", "", value)); return row; }
function setImage(image, empty, frame) { const visible = Boolean(frame?.base64); image.hidden = !visible; empty.hidden = visible; if (visible) image.src = dataImage(frame.base64, frame.format); else image.removeAttribute("src"); }
function drawRouteEvidence(canvas, scene) {
  const rect = canvas.getBoundingClientRect(); const ratio = Math.min(2, devicePixelRatio || 1); const width = Math.max(1, rect.width); const height = Math.max(1, rect.height);
  canvas.width = width * ratio; canvas.height = height * ratio; const context = canvas.getContext("2d"); context.setTransform(ratio, 0, 0, ratio, 0, 0); context.fillStyle = "#eceae5"; context.fillRect(0, 0, width, height);
  if (!scene?.bounds?.length) return; const [minX, minY, maxX, maxY] = scene.bounds; const project = ([x, y]) => [18 + ((x - minX) / (maxX - minX || 1)) * (width - 36), height - 18 - ((y - minY) / (maxY - minY || 1)) * (height - 36)];
  scene.routes.forEach((route, index) => { const points = route.path.map(project); if (points.length < 2) return; context.beginPath(); points.forEach(([x, y], i) => i ? context.lineTo(x, y) : context.moveTo(x, y)); context.strokeStyle = ROUTE_COLORS[index % ROUTE_COLORS.length]; context.lineWidth = route.selected ? 5 : 3; context.stroke(); });
}
function eventTitle(item) { const event = item.event; return event.label || event.inputKind || event.actionId || event.observationId || item.kind.replaceAll("-", " ").toUpperCase(); }
function eventSummary(item) { const event = item.event; return event.summary || event.detail || event.modelId || event.source || item.topic; }
function eventIcon(kind) { if (kind === "brain-trace") return "AI"; if (kind === "gemma-input") return "{}"; if (kind.includes("image")) return "IMG"; if (kind === "action-result") return "✓"; if (kind === "observation") return "OBS"; if (kind.includes("candidate") || kind.includes("scene")) return "MAP"; return "EV"; }
function safeJson(value) { const projected = value?.base64 ? { ...value, base64: `[binary ${value.base64.length} base64 chars]` } : value; try { return JSON.stringify(projected, null, 2); } catch { return String(projected); } }
function node(tag, className = "", text = "") { const value = document.createElement(tag); if (className) value.className = className; if (text !== "") value.textContent = text; return value; }
function camel(value) { return value.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()); }
function percent(value) { return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "—"; }
function fixed(value, digits = 2) { return Number.isFinite(value) ? value.toFixed(digits) : "—"; }
function meters(value) { return Number.isFinite(value) ? `${value.toFixed(2)} m` : "—"; }
function ms(value) { return Number.isFinite(value) ? `${Math.round(value)} ms` : "—"; }
function frameRate(value) { return Number.isFinite(value) && value > 0 ? (1000 / value).toFixed(1) : "—"; }
function seconds(value) { return Number.isFinite(value) ? (value / 1000).toFixed(3) : "0.000"; }
function clock(value) { const secondsValue = Math.max(0, Math.floor(value / 1000)); return `${String(Math.floor(secondsValue / 60)).padStart(2, "0")}:${String(secondsValue % 60).padStart(2, "0")}`; }
function shortHash(value) { return value ? `${value.slice(0, 12)}…` : "—"; }
function dataImage(base64, format) { return `data:image/${String(format).includes("png") ? "png" : "jpeg"};base64,${base64}`; }
