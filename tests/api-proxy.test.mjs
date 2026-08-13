import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const routeSource = fs.readFileSync(
  path.join(process.cwd(), "app", "api", "kb", "[...path]", "route.ts"),
  "utf8",
);
const serverSource = fs.readFileSync(
  path.join(process.cwd(), "scripts", "start-web.mjs"),
  "utf8",
);

test("knowledge proxy preserves PDF range request and response headers", () => {
  assert.match(routeSource, /request\.headers\.get\("range"\)/);
  assert.match(routeSource, /headers\.set\("range", range\)/);
  assert.match(routeSource, /"accept-ranges"/);
  assert.match(routeSource, /"content-range"/);
  assert.match(routeSource, /export const HEAD = proxy/);
});

test("production web server sends knowledge API streams directly to Agent", () => {
  assert.match(serverSource, /requestUrl\.pathname\.startsWith\("\/api\/kb\/"\)/);
  assert.match(serverSource, /proxyToAgent\(request, response, requestUrl\)/);
  assert.match(serverSource, /slice\("\/api\/kb"\.length\)/);
  assert.match(serverSource, /request\.pause\(\)/);
  assert.match(serverSource, /proxyRequest\.once\("drain"/);
});

test("knowledge proxy streams large request bodies instead of buffering them", () => {
  assert.match(routeSource, /body = method[^;]+request\.body/s);
  assert.match(routeSource, /requestInit\.duplex = "half"/);
  assert.doesNotMatch(routeSource, /request\.arrayBuffer\(\)/);
  assert.match(routeSource, /headers\.set\("content-length", contentLength\)/);
});
