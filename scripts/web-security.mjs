const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

export const DEFAULT_MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024 * 1024;
const MAX_CONFIGURABLE_REQUEST_BODY_BYTES = 2 * 1024 * 1024 * 1024;

function normalizeHostname(value) {
  const candidate = String(value ?? "").trim().toLowerCase();
  if (
    !candidate ||
    candidate.length > 253 ||
    /[\s/@\\]/.test(candidate)
  ) {
    return null;
  }
  try {
    return new URL(`http://${candidate}`).hostname.toLowerCase();
  } catch {
    return null;
  }
}

export function parseAllowedHosts(value) {
  const hosts = new Set(
    String(value ?? "")
      .split(",")
      .map(normalizeHostname)
      .filter(Boolean),
  );
  if (hosts.size === 0) {
    throw new Error("JINGAO_WEB_HOSTS 至少需要配置一个合法主机名。");
  }
  return hosts;
}

export function isAllowedHost(hostHeader, allowedHosts) {
  const hostname = normalizeHostname(hostHeader);
  return hostname !== null && allowedHosts.has(hostname);
}

export function parseMaxRequestBodyBytes(value) {
  if (value === undefined || value === null || value === "") {
    return DEFAULT_MAX_REQUEST_BODY_BYTES;
  }
  const parsed = Number.parseInt(String(value), 10);
  if (
    !Number.isSafeInteger(parsed) ||
    parsed < 64 * 1024 ||
    parsed > MAX_CONFIGURABLE_REQUEST_BODY_BYTES
  ) {
    throw new Error(
      "JINGAO_WEB_MAX_REQUEST_BODY_BYTES 必须在 65536 到 2147483648 之间。",
    );
  }
  return parsed;
}

export function declaredBodyTooLarge(headers, maximumBytes) {
  const rawLength = headers["content-length"];
  if (rawLength === undefined) return false;
  const value = Array.isArray(rawLength) ? rawLength[0] : rawLength;
  if (!/^\d+$/.test(String(value))) return true;
  return Number(value) > maximumBytes;
}

export function sanitizeProxyHeaders(headers, fallbackHost) {
  const sanitized = {};
  for (const [name, value] of Object.entries(headers)) {
    if (value === undefined || HOP_BY_HOP_HEADERS.has(name.toLowerCase())) {
      continue;
    }
    sanitized[name] = value;
  }
  sanitized.host = headers.host ?? fallbackHost;
  return sanitized;
}

export function securityHeaders(requestHeaders = {}) {
  const forwardedProto = String(requestHeaders["x-forwarded-proto"] ?? "")
    .split(",", 1)[0]
    .trim()
    .toLowerCase();
  const headers = {
    "Content-Security-Policy": [
      "default-src 'self'",
      "base-uri 'self'",
      "connect-src 'self'",
      "font-src 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
      "img-src 'self' data: blob:",
      "object-src 'none'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "worker-src 'self' blob:",
    ].join("; "),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy":
      "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  };
  if (forwardedProto === "https") {
    headers["Strict-Transport-Security"] =
      "max-age=31536000; includeSubDomains";
  }
  return headers;
}

export function mergeSecurityHeaders(upstreamHeaders, requestHeaders = {}) {
  return {
    ...upstreamHeaders,
    ...securityHeaders(requestHeaders),
  };
}
