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
const pageSource = fs.readFileSync(
  path.join(process.cwd(), "app", "page.tsx"),
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

test("project collaborator updates allow PUT through both proxy layers", () => {
  assert.match(routeSource, /export const PUT = proxy/);
  assert.match(serverSource, /\["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"\]/);
  assert.match(serverSource, /Allow: "GET, HEAD, POST, PUT, PATCH, DELETE"/);
});

test("staff removal allows DELETE through both proxy layers", () => {
  assert.match(routeSource, /export const DELETE = proxy/);
  assert.match(serverSource, /\["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"\]/);
});

test("folder uploads retry transient tunnel failures and retain only failed files", () => {
  assert.match(pageSource, /uploadOneFileWithRetry/);
  assert.match(pageSource, /new Set\(\[0, 404, 408, 425, 429, 500, 502, 503, 504\]\)/);
  assert.match(pageSource, /const delays = \[3_000, 6_000, 12_000\]/);
  assert.match(pageSource, /setUploadFiles\(failed\.map\(\(item\) => item\.file\)\)/);
  assert.match(pageSource, /已保留在待上传列表/);
});

test("login has a bounded timeout without imposing it on large uploads", () => {
  assert.match(pageSource, /"v1\/auth\/login", \{\s*method: "POST",\s*signal: AbortSignal\.timeout\(20_000\)/);
  assert.match(pageSource, /登录服务响应超时/);
});
