const PAPER = [234, 244, 244];
const UNKNOWN = [213, 230, 232];
const FREE = [20, 57, 204];
const UNCERTAIN = [38, 79, 214];
const WALL = [255, 86, 45];

export class TacticalMap {
  constructor(canvas, emptyState) {
    this.canvas = canvas;
    this.emptyState = emptyState;
    this.visible = false;
    this.image = null;
    this.loadRevision = 0;
    // Live MetaView already contains evidence-backed occupancy, routes, depth
    // footprint and robot pose. It is displayed verbatim.
    this.options = { occupancy: true, routes: true, fov: true, grid: true, tactical: false };
    this.headingDeg = 0;
    this.cached = null;
    this.robotPixel = null;
    this.resizeObserver = new ResizeObserver(() => this.render());
    this.resizeObserver.observe(canvas.parentElement);
    this.render();
  }

  setFrame(base64, format = "jpeg") {
    if (!base64) return;
    const revision = ++this.loadRevision;
    const image = new Image();
    image.onload = () => {
      if (revision !== this.loadRevision) return;
      this.image = image;
      this.rebuildCache();
      this.render();
    };
    image.src = `data:image/${format.includes("png") ? "png" : "jpeg"};base64,${base64}`;
  }

  setVisible(visible) {
    this.visible = visible;
    this.canvas.hidden = !visible;
    if (visible) this.render();
  }

  hasFrame() {
    return Boolean(this.cached);
  }

  setHeading(headingDeg) {
    if (Number.isFinite(headingDeg)) this.headingDeg = headingDeg;
    this.render();
  }

  setOption(name, enabled) {
    if (!(name in this.options)) return;
    this.options[name] = enabled;
    if (["occupancy", "routes", "tactical"].includes(name)) this.rebuildCache();
    this.render();
  }

  rebuildCache() {
    if (!this.image) return;
    const source = document.createElement("canvas");
    source.width = this.image.naturalWidth;
    source.height = this.image.naturalHeight;
    const context = source.getContext("2d", { willReadFrequently: true });
    context.drawImage(this.image, 0, 0);
    if (!this.options.tactical) {
      this.cached = source;
      this.robotPixel = locateRobot(context.getImageData(0, 0, source.width, source.height));
      return;
    }
    const pixels = context.getImageData(0, 0, source.width, source.height);
    this.robotPixel = locateRobot(pixels);
    remapPixels(pixels.data, this.options);
    context.putImageData(pixels, 0, 0);
    this.cached = source;
  }

  render() {
    if (!this.visible) return;
    const { width, height, ratio } = fitCanvas(this.canvas);
    const context = this.canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    if (!this.cached) {
      context.fillStyle = "#eaf4f4";
      context.fillRect(0, 0, width, height);
      this.emptyState.hidden = false;
      return;
    }
    this.emptyState.hidden = true;
    context.fillStyle = this.options.tactical ? "#eaf4f4" : "#06090a";
    context.fillRect(0, 0, width, height);
    const rect = contain(this.cached.width, this.cached.height, width, height);
    context.imageSmoothingEnabled = false;
    context.drawImage(this.cached, rect.x, rect.y, rect.width, rect.height);
  }
}

function remapPixels(data, options) {
  for (let index = 0; index < data.length; index += 4) {
    const red = data[index];
    const green = data[index + 1];
    const blue = data[index + 2];
    const route = routeKind(red, green, blue);
    let color;
    if (route) color = options.routes ? routeColor(route) : UNKNOWN;
    else if (!options.occupancy) color = PAPER;
    else if (red > 125 && red > green * 1.45 && red > blue * 1.45) color = WALL;
    else if (red < 44 && green < 44 && blue < 44) color = PAPER;
    else if (blue > red * 1.2 && green > red * 1.15) color = FREE;
    else if (red < 105 && green < 105 && blue < 105) color = UNCERTAIN;
    else color = [red, green, blue];
    data[index] = color[0];
    data[index + 1] = color[1];
    data[index + 2] = color[2];
  }
}

function locateRobot(imageData) {
  let count = 0;
  let sumX = 0;
  let sumY = 0;
  const { data, width, height } = imageData;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      const red = data[index];
      const green = data[index + 1];
      const blue = data[index + 2];
      if (red > 45 && red < 150 && green > 175 && green - red > 60 && green - blue > 70) {
        count += 1;
        sumX += x;
        sumY += y;
      }
    }
  }
  return count > 12 ? { x: sumX / count, y: sumY / count } : null;
}

function routeKind(red, green, blue) {
  if (green > 175 && green > red + 55 && green > blue + 55) return "robot";
  if (red > 160 && green > 145 && blue < 125) return "yellow";
  if (red > 145 && blue > 145 && green < 175) return "magenta";
  if (blue > 155 && green > 125 && red < 145) return "cyan";
  return null;
}

function routeColor(kind) {
  if (kind === "robot") return [37, 215, 105];
  if (kind === "yellow") return [255, 187, 0];
  if (kind === "magenta") return [237, 55, 186];
  return [17, 181, 221];
}

function drawFov(context, x, y, headingDeg, radius) {
  const heading = (-headingDeg * Math.PI) / 180;
  const halfAngle = (34 * Math.PI) / 180;
  context.save();
  context.beginPath();
  context.moveTo(x, y);
  context.arc(x, y, radius, heading - halfAngle, heading + halfAngle);
  context.closePath();
  context.fillStyle = "rgba(255, 212, 49, 0.14)";
  context.fill();
  context.strokeStyle = "rgba(159, 104, 0, 0.7)";
  context.lineWidth = 1;
  context.setLineDash([6, 5]);
  context.stroke();
  context.restore();
}

function drawGrid(context, width, height) {
  context.save();
  context.strokeStyle = "rgba(15, 72, 91, 0.09)";
  context.lineWidth = 1;
  for (let x = 32; x < width; x += 48) {
    context.beginPath(); context.moveTo(x, 0); context.lineTo(x, height); context.stroke();
  }
  for (let y = 32; y < height; y += 48) {
    context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke();
  }
  context.restore();
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
  return { width, height, ratio };
}

function contain(sourceWidth, sourceHeight, width, height) {
  const scale = Math.min(width / sourceWidth, height / sourceHeight);
  const resultWidth = sourceWidth * scale;
  const resultHeight = sourceHeight * scale;
  return {
    x: (width - resultWidth) / 2,
    y: (height - resultHeight) / 2,
    width: resultWidth,
    height: resultHeight,
  };
}
