import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(resolve(root, "index.html"), "utf8");

test("approved navigation exposes five named views with one initial current page", () => {
  const names = [...html.matchAll(/data-view-target="([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(names, ["mission", "timeline", "map", "sensors", "sessions"]);
  assert.equal((html.match(/aria-current="page"/g) || []).length, 1);
  for (const name of names) assert.match(html, new RegExp(`data-view="${name}"`));
});

test("interactive canvas surfaces and controls have accessible names", () => {
  for (const id of ["spatial-canvas", "metaview-canvas", "camera-canvas", "detail-route-canvas"]) {
    assert.match(html, new RegExp(`<canvas[^>]+id="${id}"[^>]+aria-label="[^"]+"`));
  }
  for (const id of ["map-view-3d", "map-view-2d", "map-follow", "map-top", "map-reset"]) {
    assert.match(html, new RegExp(`<button[^>]+id="${id}"`));
  }
});

test("brain timeline exposes an explicit all-versus-Gemma-only audit filter", () => {
  assert.match(html, /id="timeline-filter-all"[^>]*>TODOS<\/button>/);
  assert.match(html, /id="timeline-filter-gemma"[^>]*>SOLO GEMMA<\/button>/);
  const renderer = readFileSync(resolve(root, "scripts/render.js"), "utf8");
  for (const category of ["TOOL_REQUEST", "TOOL_RESULT", "MODEL_RESPONSE", "CANCELED"]) {
    assert.match(renderer, new RegExp(`"${category}"`));
  }
  assert.match(renderer, /no cadena de pensamiento privada/i);
});

test("production entrypoint has no synthetic or demo runtime path", () => {
  const main = readFileSync(resolve(root, "scripts/main.js"), "utf8");
  const tactical = readFileSync(resolve(root, "scripts/tactical-map.js"), "utf8");
  assert.doesNotMatch(main, /demo|synthetic|mock/i);
  assert.doesNotMatch(tactical, /drawDemo|demoFree|demoWall|demoDepth/);
  assert.doesNotMatch(html, /demo=1|demo\.js/);
});

test("every getElementById dependency exists in the document", () => {
  const scripts = ["main.js", "render.js"].map((name) => readFileSync(resolve(root, "scripts", name), "utf8")).join("\n");
  const ids = [...scripts.matchAll(/getElementById\("([^"]+)"\)/g)].map((match) => match[1]);
  for (const id of ids) assert.match(html, new RegExp(`id="${id}"`), `missing #${id}`);
});

test("handwritten production modules stay below 400 lines", () => {
  const files = ["server.py", "scripts/contracts.js", "scripts/main.js", "scripts/render.js", "scripts/rosbridge.js", "scripts/session-api.js", "scripts/spatial-map.js", "scripts/store.js", "scripts/tactical-map.js"];
  for (const file of files) {
    const lines = readFileSync(resolve(root, file), "utf8").split("\n").length - 1;
    assert.ok(lines < 400, `${file} has ${lines} lines`);
  }
});
