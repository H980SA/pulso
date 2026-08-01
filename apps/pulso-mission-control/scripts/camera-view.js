export class CameraView {
  constructor(canvas, emptyState) {
    this.canvas = canvas;
    this.emptyState = emptyState;
    this.image = null;
    this.tracks = [];
    this.loadRevision = 0;
    this.resizeObserver = new ResizeObserver(() => this.render());
    this.resizeObserver.observe(canvas.parentElement);
    this.render();
  }

  setFrame(base64, format = "jpeg") {
    if (!base64) return;
    this.loadUrl(`data:image/${format.includes("png") ? "png" : "jpeg"};base64,${base64}`);
  }

  setTracks(tracks = []) {
    this.tracks = tracks;
    this.render();
  }

  loadUrl(url) {
    const revision = ++this.loadRevision;
    const image = new Image();
    image.onload = () => {
      if (revision !== this.loadRevision) return;
      this.image = image;
      this.render();
    };
    image.src = url;
  }

  render() {
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    const width = Math.max(1, this.canvas.clientWidth);
    const height = Math.max(1, this.canvas.clientHeight);
    this.canvas.width = Math.round(width * ratio);
    this.canvas.height = Math.round(height * ratio);
    const context = this.canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.fillStyle = "#020303";
    context.fillRect(0, 0, width, height);
    if (!this.image) {
      this.emptyState.hidden = false;
      return;
    }
    this.emptyState.hidden = true;
    const rect = cover(this.image.naturalWidth, this.image.naturalHeight, width, height);
    context.drawImage(this.image, rect.x, rect.y, rect.width, rect.height);
    this.tracks.forEach((track, index) => drawTrack(context, track, rect, index));
  }
}

function drawTrack(context, track, rect, index) {
  if (!track.boxNorm) return;
  const [left, top, right, bottom] = track.boxNorm;
  const x = rect.x + left * rect.width;
  const y = rect.y + top * rect.height;
  const width = (right - left) * rect.width;
  const height = (bottom - top) * rect.height;
  const color = index % 2 ? "#49d8ed" : "#fa5bcc";
  context.save();
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.strokeRect(x, y, width, height);
  const confidence = track.confidence === null ? "—" : `${Math.round(track.confidence * 100)}%`;
  const label = `${track.id} / ${track.label.toUpperCase()} / ${confidence}`;
  context.font = "600 11px monospace";
  const textWidth = context.measureText(label).width;
  context.fillStyle = color;
  context.fillRect(x, Math.max(0, y - 20), textWidth + 12, 20);
  context.fillStyle = "#050808";
  context.fillText(label, x + 6, Math.max(14, y - 6));
  context.restore();
}

function cover(sourceWidth, sourceHeight, width, height) {
  const scale = Math.max(width / sourceWidth, height / sourceHeight);
  const resultWidth = sourceWidth * scale;
  const resultHeight = sourceHeight * scale;
  return {
    x: (width - resultWidth) / 2,
    y: (height - resultHeight) / 2,
    width: resultWidth,
    height: resultHeight,
  };
}
