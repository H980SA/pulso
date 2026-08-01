const ROUTE_COLORS = ["#e9bd00", "#ea42b3", "#08a9cb", "#23bf64", "#f14d2f", "#826de8"];
const DEG = Math.PI / 180;

/**
 * Interactive 3D projection of the evidence-only MetaView scene.
 *
 * This intentionally uses Canvas2D instead of a remote 3D dependency: every
 * point comes from ROS and the operator can orbit, pan, zoom, follow or reset
 * without a CDN or a synthetic environment mesh.
 */
export class SpatialMap {
  constructor(canvas, emptyState, { onFollowChange = () => {} } = {}) {
    this.canvas = canvas;
    this.emptyState = emptyState;
    this.scene = null;
    this.visible = true;
    this.follow = true;
    this.onFollowChange = onFollowChange;
    this.camera = {
      target: [0, 0, 0.05],
      yaw: -38 * DEG,
      pitch: 57 * DEG,
      distance: 5.5,
    };
    this.pointer = null;
    this.resizeObserver = new ResizeObserver(() => this.render());
    this.resizeObserver.observe(canvas.parentElement);
    this.installControls();
    this.render();
  }

  setScene(scene) {
    const first = !this.scene;
    this.scene = scene;
    if (this.follow && scene?.robot?.position) {
      const [x, y, z = 0] = scene.robot.position;
      this.camera.target = [x, y, Math.max(0.05, z)];
    }
    if (first) {
      const preserveFollow = this.follow;
      this.frameAll();
      if (preserveFollow) this.setFollow(true);
    }
    this.syncEmptyState();
    this.render();
  }

  setVisible(visible) {
    this.visible = visible;
    this.canvas.hidden = !visible;
    this.syncEmptyState();
    if (visible) this.render();
  }

  setFollow(enabled) {
    this.follow = enabled;
    if (enabled && this.scene?.robot?.position) {
      const [x, y, z = 0] = this.scene.robot.position;
      this.camera.target = [x, y, Math.max(0.05, z)];
    }
    this.onFollowChange(this.follow);
    this.render();
  }

  topView() {
    this.camera.pitch = 88 * DEG;
    this.camera.yaw = 0;
    this.render();
  }

  frameAll() {
    const bounds = this.scene?.bounds;
    if (bounds?.length === 4) {
      const [minX, minY, maxX, maxY] = bounds;
      this.camera.target = [(minX + maxX) / 2, (minY + maxY) / 2, 0.05];
      this.camera.distance = clamp(Math.hypot(maxX - minX, maxY - minY) * 0.9, 2.2, 22);
    } else if (this.scene?.robot?.position) {
      this.camera.target = [...this.scene.robot.position];
      this.camera.distance = 5.5;
    }
    this.follow = false;
    this.onFollowChange(this.follow);
    this.render();
  }

  focusCandidate(candidateId) {
    const route = this.scene?.routes?.find((item) => item.id === candidateId);
    if (!route?.position) return;
    this.follow = false;
    this.onFollowChange(this.follow);
    this.camera.target = [route.position[0], route.position[1], 0.05];
    this.camera.distance = clamp(this.camera.distance, 2.0, 8.0);
    this.render();
  }

  installControls() {
    this.canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    this.canvas.addEventListener("pointerdown", (event) => {
      if (!this.visible) return;
      this.canvas.setPointerCapture(event.pointerId);
      this.pointer = {
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        mode: event.shiftKey || event.button !== 0 ? "pan" : "orbit",
      };
    });
    this.canvas.addEventListener("pointermove", (event) => {
      if (!this.pointer || this.pointer.id !== event.pointerId) return;
      const dx = event.clientX - this.pointer.x;
      const dy = event.clientY - this.pointer.y;
      this.pointer.x = event.clientX;
      this.pointer.y = event.clientY;
      if (this.pointer.mode === "orbit") {
        this.camera.yaw -= dx * 0.008;
        this.camera.pitch = clamp(this.camera.pitch + dy * 0.008, 9 * DEG, 89 * DEG);
      } else {
        const amount = this.camera.distance * 0.0016;
        const right = [Math.cos(this.camera.yaw), Math.sin(this.camera.yaw), 0];
        const forward = [-Math.sin(this.camera.yaw), Math.cos(this.camera.yaw), 0];
        this.camera.target[0] += (-dx * right[0] + dy * forward[0]) * amount;
        this.camera.target[1] += (-dx * right[1] + dy * forward[1]) * amount;
        this.follow = false;
        this.onFollowChange(this.follow);
      }
      this.render();
    });
    const release = (event) => {
      if (this.pointer?.id === event.pointerId) this.pointer = null;
    };
    this.canvas.addEventListener("pointerup", release);
    this.canvas.addEventListener("pointercancel", release);
    this.canvas.addEventListener("wheel", (event) => {
      if (!this.visible) return;
      event.preventDefault();
      this.camera.distance = clamp(this.camera.distance * Math.exp(event.deltaY * 0.0012), 0.8, 30);
      this.render();
    }, { passive: false });
    this.canvas.addEventListener("dblclick", () => this.frameAll());
  }

  syncEmptyState() {
    if (!this.visible) return;
    this.emptyState.hidden = Boolean(this.scene);
  }

  render() {
    if (!this.visible) return;
    const { context, width, height } = fitCanvas(this.canvas);
    context.clearRect(0, 0, width, height);
    drawBackground(context, width, height);
    if (!this.scene) return;
    const camera = buildCamera(this.camera, width, height);
    drawGroundGrid(context, camera, this.scene.bounds);
    drawMapEvidence(context, camera, this.scene);
    drawScanFootprint(context, camera, this.scene.scanFootprint);
    drawRoutes(context, camera, this.scene.routes);
    drawRobot(context, camera, this.scene.robot);
    drawAxis(context, camera, this.camera.target);
  }
}

export function buildCamera(camera, width, height) {
  const cp = Math.cos(camera.pitch);
  const position = [
    camera.target[0] + camera.distance * cp * Math.sin(camera.yaw),
    camera.target[1] - camera.distance * cp * Math.cos(camera.yaw),
    camera.target[2] + camera.distance * Math.sin(camera.pitch),
  ];
  const forward = normalize(subtract(camera.target, position));
  let right = normalize(cross(forward, [0, 0, 1]));
  if (length(right) < 1e-6) right = [1, 0, 0];
  const up = normalize(cross(right, forward));
  return {
    position,
    forward,
    right,
    up,
    width,
    height,
    focal: Math.min(width, height) * 0.92,
  };
}

export function projectPoint(point, camera) {
  const relative = subtract(point, camera.position);
  const depth = dot(relative, camera.forward);
  if (depth <= 0.025) return null;
  return {
    x: camera.width / 2 + (dot(relative, camera.right) * camera.focal) / depth,
    y: camera.height / 2 - (dot(relative, camera.up) * camera.focal) / depth,
    depth,
  };
}

function drawBackground(context, width, height) {
  const gradient = context.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, "#dce9e9");
  gradient.addColorStop(0.68, "#edf5f4");
  gradient.addColorStop(1, "#cadbdc");
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);
}

function drawGroundGrid(context, camera, bounds) {
  const safe = bounds?.length === 4 ? bounds : [-5, -5, 5, 5];
  const minX = Math.floor(safe[0]);
  const minY = Math.floor(safe[1]);
  const maxX = Math.ceil(safe[2]);
  const maxY = Math.ceil(safe[3]);
  context.save();
  context.lineWidth = 1;
  for (let x = minX; x <= maxX; x += 1) {
    strokeWorldLine(context, camera, [[x, minY, 0], [x, maxY, 0]], x === 0 ? "rgba(0,115,140,.35)" : "rgba(48,94,101,.12)");
  }
  for (let y = minY; y <= maxY; y += 1) {
    strokeWorldLine(context, camera, [[minX, y, 0], [maxX, y, 0]], y === 0 ? "rgba(0,115,140,.35)" : "rgba(48,94,101,.12)");
  }
  context.restore();
}

function drawMapEvidence(context, camera, scene) {
  const free = (scene.map?.freePoints || []).map((point) => ({ point: [point[0], point[1], 0.008], kind: "free" }));
  const occupied = (scene.map?.occupiedPoints || []).map((point) => ({ point: [point[0], point[1], 0.045], kind: "occupied" }));
  const depth = (scene.depth?.points || []).map((point) => ({ point, kind: "depth" }));
  const projected = [...free, ...occupied, ...depth]
    .map((item) => ({ ...item, screen: projectPoint(item.point, camera) }))
    .filter((item) => item.screen)
    .sort((a, b) => b.screen.depth - a.screen.depth);
  for (const item of projected) {
    const attenuation = clamp(4.4 / item.screen.depth, 0.55, 4.2);
    if (item.kind === "free") {
      context.fillStyle = "rgba(19,89,241,.42)";
      square(context, item.screen.x, item.screen.y, clamp(attenuation * 0.9, 0.8, 3.3));
    } else if (item.kind === "occupied") {
      context.fillStyle = "rgba(255,76,42,.94)";
      square(context, item.screen.x, item.screen.y, clamp(attenuation * 1.7, 1.4, 6));
    } else {
      const z = item.point[2];
      context.fillStyle = z > 0.75 ? "rgba(250,91,204,.82)" : "rgba(12,154,191,.76)";
      context.beginPath();
      context.arc(item.screen.x, item.screen.y, clamp(attenuation * 0.75, 0.65, 3.4), 0, Math.PI * 2);
      context.fill();
    }
  }
}

function drawScanFootprint(context, camera, points) {
  if (!points?.length) return;
  const projected = points.map((point) => projectPoint(point, camera)).filter(Boolean);
  if (projected.length < 2) return;
  context.save();
  context.beginPath();
  projected.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
  context.closePath();
  context.fillStyle = "rgba(255,212,49,.10)";
  context.strokeStyle = "rgba(143,96,0,.48)";
  context.setLineDash([5, 5]);
  context.fill();
  context.stroke();
  context.restore();
}

function drawRoutes(context, camera, routes) {
  (routes || []).forEach((route, index) => {
    const color = ROUTE_COLORS[index % ROUTE_COLORS.length];
    const path = (route.path || []).map(([x, y, z = 0]) => [x, y, z + 0.08]);
    if (path.length < 2) return;
    context.save();
    context.lineWidth = route.selected ? 6 : 3;
    context.shadowColor = color;
    context.shadowBlur = route.selected ? 10 : 3;
    strokeWorldLine(context, camera, path, color);
    context.shadowBlur = 0;
    const endpoint = projectPoint(path.at(-1), camera);
    if (endpoint) {
      context.fillStyle = color;
      context.beginPath();
      context.arc(endpoint.x, endpoint.y, route.selected ? 14 : 11, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = "#071012";
      context.font = "800 11px ui-monospace, monospace";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText(route.label || String.fromCharCode(65 + index), endpoint.x, endpoint.y + 0.5);
      context.fillStyle = "#26444c";
      context.font = "700 9px ui-monospace, monospace";
      context.textAlign = "left";
      context.fillText(`${route.type} · ${route.id}`, endpoint.x + 17, endpoint.y + 3);
    }
    context.restore();
  });
}

function drawRobot(context, camera, robot) {
  if (!robot?.position) return;
  const [x, y, z = 0] = robot.position;
  const heading = (robot.headingDeg || 0) * DEG;
  const tip = [x + Math.cos(heading) * 0.34, y + Math.sin(heading) * 0.34, z + 0.12];
  const left = [x + Math.cos(heading + 2.45) * 0.22, y + Math.sin(heading + 2.45) * 0.22, z + 0.08];
  const right = [x + Math.cos(heading - 2.45) * 0.22, y + Math.sin(heading - 2.45) * 0.22, z + 0.08];
  const points = [tip, left, right].map((point) => projectPoint(point, camera));
  if (points.some((point) => !point)) return;
  context.save();
  context.beginPath();
  context.moveTo(points[0].x, points[0].y);
  context.lineTo(points[1].x, points[1].y);
  context.lineTo(points[2].x, points[2].y);
  context.closePath();
  context.fillStyle = "#12b95c";
  context.shadowColor = "rgba(18,185,92,.55)";
  context.shadowBlur = 12;
  context.fill();
  context.shadowBlur = 0;
  const label = projectPoint([x, y, z + 0.42], camera);
  if (label) {
    context.fillStyle = "#153740";
    context.font = "800 10px ui-monospace, monospace";
    context.textAlign = "center";
    context.fillText(`PULSO · ${x.toFixed(2)}, ${y.toFixed(2)} · ${Math.round(robot.headingDeg || 0)}°`, label.x, label.y);
  }
  context.restore();
}

function drawAxis(context, camera, target) {
  const origin = [target[0], target[1], 0.01];
  const length = 0.45;
  strokeWorldLine(context, camera, [origin, [origin[0] + length, origin[1], origin[2]]], "rgba(239,67,52,.7)");
  strokeWorldLine(context, camera, [origin, [origin[0], origin[1] + length, origin[2]]], "rgba(15,123,235,.7)");
  strokeWorldLine(context, camera, [origin, [origin[0], origin[1], origin[2] + length]], "rgba(26,150,80,.7)");
}

function strokeWorldLine(context, camera, points, color) {
  const projected = points.map((point) => projectPoint(point, camera));
  let drawing = false;
  context.beginPath();
  for (const point of projected) {
    if (!point) {
      drawing = false;
      continue;
    }
    if (!drawing) context.moveTo(point.x, point.y);
    else context.lineTo(point.x, point.y);
    drawing = true;
  }
  context.strokeStyle = color;
  context.stroke();
}

function fitCanvas(canvas) {
  const ratio = Math.min(2, window.devicePixelRatio || 1);
  const width = Math.max(1, canvas.clientWidth);
  const height = Math.max(1, canvas.clientHeight);
  const targetWidth = Math.round(width * ratio);
  const targetHeight = Math.round(height * ratio);
  if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
    canvas.width = targetWidth;
    canvas.height = targetHeight;
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function square(context, x, y, size) {
  context.fillRect(x - size / 2, y - size / 2, size, size);
}

function subtract(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

function length(vector) {
  return Math.sqrt(dot(vector, vector));
}

function normalize(vector) {
  const magnitude = length(vector);
  return magnitude <= 1e-9 ? [0, 0, 0] : vector.map((value) => value / magnitude);
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}
