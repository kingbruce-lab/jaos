import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_MAX_REQUEST_BODY_BYTES,
  declaredBodyTooLarge,
  isAllowedHost,
  mergeSecurityHeaders,
  parseAllowedHosts,
  parseMaxRequestBodyBytes,
  sanitizeProxyHeaders,
  securityHeaders,
} from "../scripts/web-security.mjs";

test("host allowlist accepts configured names with ports and rejects spoofing", () => {
  const hosts = parseAllowedHosts(
    "localhost,127.0.0.1,web,jadj-nas.local,knowledge.jingao.club",
  );

  assert.equal(isAllowedHost("knowledge.jingao.club", hosts), true);
  assert.equal(isAllowedHost("knowledge.jingao.club:443", hosts), true);
  assert.equal(isAllowedHost("JADJ-NAS.LOCAL:3000", hosts), true);
  assert.equal(isAllowedHost("web:3000", hosts), true);
  assert.equal(isAllowedHost("evil.example", hosts), false);
  assert.equal(isAllowedHost("knowledge.jingao.club@evil.example", hosts), false);
  assert.equal(isAllowedHost("knowledge.jingao.club/evil", hosts), false);
  assert.equal(isAllowedHost("", hosts), false);
});

test("request body limit is bounded and detects invalid or oversized declarations", () => {
  assert.equal(parseMaxRequestBodyBytes(undefined), DEFAULT_MAX_REQUEST_BODY_BYTES);
  assert.equal(parseMaxRequestBodyBytes("1048576"), 1048576);
  assert.throws(() => parseMaxRequestBodyBytes("1024"));
  assert.throws(() => parseMaxRequestBodyBytes("not-a-number"));

  assert.equal(declaredBodyTooLarge({}, 100), false);
  assert.equal(declaredBodyTooLarge({ "content-length": "100" }, 100), false);
  assert.equal(declaredBodyTooLarge({ "content-length": "101" }, 100), true);
  assert.equal(declaredBodyTooLarge({ "content-length": "-1" }, 100), true);
});

test("hop-by-hop headers are removed before the internal proxy", () => {
  const headers = sanitizeProxyHeaders(
    {
      authorization: "Bearer test",
      connection: "keep-alive",
      "content-type": "application/json",
      host: "knowledge.jingao.club",
      "transfer-encoding": "chunked",
      upgrade: "websocket",
    },
    "localhost:3000",
  );

  assert.equal(headers.authorization, "Bearer test");
  assert.equal(headers["content-type"], "application/json");
  assert.equal(headers.host, "knowledge.jingao.club");
  assert.equal(headers.connection, undefined);
  assert.equal(headers["transfer-encoding"], undefined);
  assert.equal(headers.upgrade, undefined);
});

test("security headers deny framing and only emit HSTS for forwarded HTTPS", () => {
  const plain = securityHeaders({});
  const secure = securityHeaders({ "x-forwarded-proto": "https" });

  assert.equal(plain["X-Frame-Options"], "DENY");
  assert.match(plain["Content-Security-Policy"], /frame-ancestors 'none'/);
  assert.equal(plain["Strict-Transport-Security"], undefined);
  assert.match(secure["Strict-Transport-Security"], /max-age=31536000/);

  const merged = mergeSecurityHeaders(
    {
      "cache-control": "no-store",
      "x-frame-options": "SAMEORIGIN",
    },
    { "x-forwarded-proto": "https" },
  );
  assert.equal(merged["cache-control"], "no-store");
  assert.equal(merged["X-Frame-Options"], "DENY");
});
