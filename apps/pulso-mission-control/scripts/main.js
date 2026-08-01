import { CameraView } from "./camera-view.js";
import { createRenderer } from "./render.js";
import { resolveBridgeUrl, RosbridgeClient } from "./rosbridge.js";
import { listSessions, readSession, replaySession, SessionRecorder } from "./session-api.js";
import { createMissionStore } from "./store.js";
import { SpatialMap } from "./spatial-map.js";
import { TacticalMap } from "./tactical-map.js";

const params = new URLSearchParams(window.location.search);
const replayId = params.get("session");
const mode = replayId ? "REPLAY" : "LIVE";
const bridgeUrl = resolveBridgeUrl(window.location);
const store = createMissionStore({ mode });
const tacticalMap = new TacticalMap(
  document.getElementById("metaview-canvas"),
  document.getElementById("map-empty"),
);
const followButton = document.getElementById("map-follow");
const spatialMap = new SpatialMap(
  document.getElementById("spatial-canvas"),
  document.getElementById("map-empty"),
  { onFollowChange: (enabled) => { followButton.dataset.active = String(enabled); } },
);
const cameraView = new CameraView(
  document.getElementById("camera-canvas"),
  document.getElementById("camera-empty"),
);
const render = createRenderer({ tacticalMap, spatialMap, cameraView, bridgeUrl });
let recorder = mode === "LIVE" ? new SessionRecorder({ onStatus: recorderStatus }) : null;
const client = new RosbridgeClient(bridgeUrl, {
  onStatus: (status, detail) => store.setBridge(status, detail),
  onEvent: (event, metadata) => {
    const receivedAt = performance.now();
    store.ingest(event, receivedAt, metadata);
    recorder?.record(event, metadata.topic, receivedAt);
  },
  onBridgeMessage: (event) => {
    if (event.level === "error") console.warn("rosbridge:", event.message);
  },
});

store.subscribe(render);
setInterval(() => render(store.get()), 1000);
installNavigation();
installMapControls();
installSelectionControls();
refreshSessions();

if (replayId) startPersistedReplay(replayId);
else if (params.get("autoconnect") !== "0") client.connect();

document.getElementById("connection-toggle").addEventListener("click", async () => {
  if (store.get().bridge.status === "live" || store.get().bridge.status === "connecting") {
    client.disconnect();
    await recorder?.close();
    recorder = new SessionRecorder({ onStatus: recorderStatus });
    refreshSessions();
  } else {
    client.connect();
  }
});

function installNavigation() {
  const requested = replayId ? "timeline" : params.get("view") || "mission";
  setActiveView(requested);
  document.querySelector(".primary-nav").addEventListener("click", (event) => {
    const button = event.target.closest("[data-view-target]");
    if (!button) return;
    setActiveView(button.dataset.viewTarget);
    const next = new URL(window.location.href);
    next.searchParams.set("view", button.dataset.viewTarget);
    history.replaceState(null, "", next);
  });
}

function setActiveView(name) {
  const allowed = new Set(["mission", "timeline", "map", "sensors", "sessions"]);
  const selected = allowed.has(name) ? name : "mission";
  document.querySelectorAll(".view[data-view]").forEach((view) => { view.hidden = view.dataset.view !== selected; });
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    if (button.dataset.viewTarget === selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (selected === "map") spatialMap.render();
  if (selected === "sensors") cameraView.render();
}

function installMapControls() {
  const viewport = document.getElementById("map-viewport");
  document.getElementById("map-view-3d").addEventListener("click", () => selectMapView("spatial"));
  document.getElementById("map-view-2d").addEventListener("click", () => selectMapView("flat"));
  followButton.addEventListener("click", () => spatialMap.setFollow(!spatialMap.follow));
  document.getElementById("map-top").addEventListener("click", () => spatialMap.topView());
  document.getElementById("map-reset").addEventListener("click", () => spatialMap.frameAll());
  function selectMapView(view) {
    const spatial = view === "spatial";
    viewport.dataset.view = view;
    spatialMap.setVisible(spatial);
    tacticalMap.setVisible(!spatial);
    document.getElementById("map-view-3d").dataset.active = String(spatial);
    document.getElementById("map-view-2d").dataset.active = String(!spatial);
    if (!spatial && !tacticalMap.hasFrame()) document.getElementById("map-empty").hidden = false;
  }
  selectMapView("spatial");
}

function installSelectionControls() {
  document.getElementById("timeline-filter-all").addEventListener("click", () => setTimelineFilter("all"));
  document.getElementById("timeline-filter-gemma").addEventListener("click", () => setTimelineFilter("gemma"));
  document.getElementById("event-timeline").addEventListener("click", (event) => {
    const row = event.target.closest("[data-event-id]");
    if (row) render.selectEvent(row.dataset.eventId);
  });
  document.getElementById("route-strip").addEventListener("click", (event) => {
    const row = event.target.closest("[data-candidate-id]");
    if (!row) return;
    render.selectRoute(row.dataset.candidateId);
    spatialMap.focusCandidate(row.dataset.candidateId);
  });
  document.getElementById("sessions-list").addEventListener("click", (event) => {
    const row = event.target.closest("[data-session-id]");
    if (row) render.selectSession(row.dataset.sessionId);
  });
  document.getElementById("sessions-refresh").addEventListener("click", refreshSessions);
  document.getElementById("session-replay").addEventListener("click", () => {
    const session = render.selectedSession();
    if (!session) return;
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("session", session.session_id);
    url.searchParams.set("view", "timeline");
    window.location.assign(url);
  });
}

function setTimelineFilter(filter) {
  const gemma = filter === "gemma";
  document.getElementById("timeline-filter-all").dataset.active = String(!gemma);
  document.getElementById("timeline-filter-gemma").dataset.active = String(gemma);
  render.setTimelineFilter(filter);
}

async function refreshSessions() {
  try {
    render.setSessions(await listSessions());
  } catch (error) {
    document.getElementById("session-summary").textContent = `Persistencia no disponible: ${error.message}`;
  }
}

async function startPersistedReplay(sessionId) {
  document.body.classList.add("replay-mode");
  const banner = document.getElementById("mode-banner");
  banner.hidden = false;
  banner.textContent = `REPLAY PERSISTIDO · ${sessionId} · NO CONTROLA EL ROBOT`;
  try {
    const session = await readSession(sessionId);
    store.setSession(session);
    store.setPersistence("replay", "Sesión verificada cargada desde SQLite");
    store.setBridge("replay", `Reproduciendo ${sessionId} desde SQLite`);
    await replaySession(session, (event, at, metadata) => store.ingest(event, at, metadata));
  } catch (error) {
    store.setBridge("error", error.message);
    banner.textContent = `REPLAY NO DISPONIBLE · ${sessionId}`;
  }
}

function recorderStatus(status, session, error) {
  store.setPersistence(status, error?.message || "Persistencia SQLite con hash encadenado");
  if (session) store.setSession(session);
}
