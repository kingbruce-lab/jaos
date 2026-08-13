import { spawn } from "node:child_process";
import { createReadStream, existsSync, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  declaredBodyTooLarge,
  isAllowedHost,
  mergeSecurityHeaders,
  parseAllowedHosts,
  parseMaxRequestBodyBytes,
  sanitizeProxyHeaders,
  securityHeaders,
} from "./web-security.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const clientRoot = path.join(projectRoot, "dist", "client");
const vinextCli = path.join(
  projectRoot,
  "node_modules",
  "vinext",
  "dist",
  "cli.js",
);

const publicPort = Number.parseInt(process.env.PORT ?? "3000", 10);
const publicHost = process.env.HOST ?? "0.0.0.0";
const internalPort = Number.parseInt(
  process.env.JINGAO_WEB_INTERNAL_PORT ?? String(publicPort + 1),
  10,
);
const internalHost = "127.0.0.1";
const allowedHosts = parseAllowedHosts(
  process.env.JINGAO_WEB_HOSTS ??
    "localhost,127.0.0.1,[::1],web,jadj-nas.local,192.168.2.53,knowledge.jingao.club",
);
const maximumRequestBodyBytes = parseMaxRequestBodyBytes(
  process.env.JINGAO_WEB_MAX_REQUEST_BODY_BYTES,
);
const upstreamTimeoutMilliseconds = 30 * 60 * 1000;
const agentUrl = new URL(
  process.env.JINGAO_AGENT_URL ?? "http://127.0.0.1:8000",
);
if (agentUrl.protocol !== "http:") {
  throw new Error("JINGAO_AGENT_URL 当前只支持受控 Docker 内网 HTTP 地址。");
}

if (!existsSync(path.join(clientRoot, "assets"))) {
  throw new Error("未找到前端构建产物，请先运行 pnpm run build。");
}

const contentTypes = new Map([
  [".avif", "image/avif"],
  [".css", "text/css; charset=utf-8"],
  [".gif", "image/gif"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".map", "application/json; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml; charset=utf-8"],
  [".ttf", "font/ttf"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);

function resolveStaticPath(urlPathname) {
  let decodedPathname;
  try {
    decodedPathname = decodeURIComponent(urlPathname);
  } catch {
    return null;
  }

  if (
    decodedPathname === "/" ||
    decodedPathname.startsWith("/.vite/") ||
    decodedPathname.includes("\0")
  ) {
    return null;
  }

  const candidate = path.resolve(clientRoot, `.${decodedPathname}`);
  const clientPrefix = `${path.resolve(clientRoot)}${path.sep}`;
  if (!candidate.startsWith(clientPrefix)) {
    return null;
  }

  try {
    return statSync(candidate).isFile() ? candidate : null;
  } catch {
    return null;
  }
}

function serveStatic(request, response, pathname) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return false;
  }

  const staticPath = resolveStaticPath(pathname);
  if (!staticPath) {
    return false;
  }

  const stat = statSync(staticPath);
  const extension = path.extname(staticPath).toLowerCase();
  const immutable = pathname.startsWith("/assets/");
  response.writeHead(200, {
    ...securityHeaders(request.headers),
    "Cache-Control": immutable
      ? "public, max-age=31536000, immutable"
      : "public, max-age=3600",
    "Content-Length": String(stat.size),
    "Content-Type":
      contentTypes.get(extension) ?? "application/octet-stream",
  });
  if (request.method === "HEAD") {
    response.end();
  } else {
    createReadStream(staticPath).pipe(response);
  }
  return true;
}

function sendPlain(request, response, statusCode, message, extraHeaders = {}) {
  if (response.headersSent) return;
  response.writeHead(statusCode, {
    ...securityHeaders(request.headers),
    "Cache-Control": "no-store",
    "Content-Type": "text/plain; charset=utf-8",
    ...extraHeaders,
  });
  response.end(message);
}

function proxyStream(request, response, target) {
  if (declaredBodyTooLarge(request.headers, maximumRequestBodyBytes)) {
    sendPlain(request, response, 413, "请求内容过大。");
    request.resume();
    return;
  }

  const proxyHeaders = sanitizeProxyHeaders(
    request.headers,
    target.fallbackHost,
  );
  proxyHeaders.host = target.fallbackHost;
  const proxyRequest = http.request(
    {
      hostname: target.hostname,
      port: target.port,
      method: request.method,
      path: target.path,
      headers: proxyHeaders,
    },
    (proxyResponse) => {
      response.writeHead(
        proxyResponse.statusCode ?? 502,
        proxyResponse.statusMessage,
        mergeSecurityHeaders(proxyResponse.headers, request.headers),
      );
      proxyResponse.pipe(response);
    },
  );
  proxyRequest.setTimeout(upstreamTimeoutMilliseconds, () => {
    proxyRequest.destroy(new Error("upstream timeout"));
  });

  proxyRequest.on("error", () => {
    if (!response.headersSent) {
      sendPlain(
        request,
        response,
        503,
        target.errorMessage,
        { "Retry-After": "2" },
      );
      return;
    }
    response.end();
  });

  let receivedBytes = 0;
  let rejected = false;
  request.on("data", (chunk) => {
    if (rejected) return;
    receivedBytes += chunk.length;
    if (receivedBytes > maximumRequestBodyBytes) {
      rejected = true;
      proxyRequest.destroy();
      sendPlain(request, response, 413, "请求内容过大。");
      return;
    }
    if (!proxyRequest.write(chunk)) {
      request.pause();
      proxyRequest.once("drain", () => request.resume());
    }
  });
  request.on("end", () => {
    if (!rejected) proxyRequest.end();
  });
  request.on("error", () => {
    proxyRequest.destroy();
    if (!response.headersSent) {
      sendPlain(request, response, 400, "请求读取失败。");
    }
  });
}

function proxyToVinext(request, response) {
  proxyStream(request, response, {
    hostname: internalHost,
    port: internalPort,
    path: request.url,
    fallbackHost: `${publicHost}:${publicPort}`,
    errorMessage: "京奥AI智能运营系统正在启动，请稍后刷新。",
  });
}

function proxyToAgent(request, response, requestUrl) {
  const upstreamPath = requestUrl.pathname.slice("/api/kb".length) || "/";
  proxyStream(request, response, {
    hostname: agentUrl.hostname,
    port: agentUrl.port || "80",
    path: `${upstreamPath}${requestUrl.search}`,
    fallbackHost: agentUrl.host,
    errorMessage: "知识服务暂未启动，请联系管理员。",
  });
}

const vinextProcess = spawn(
  process.execPath,
  [vinextCli, "start", "-p", String(internalPort), "-H", internalHost],
  {
    cwd: projectRoot,
    env: { ...process.env, PORT: String(internalPort) },
    stdio: "inherit",
  },
);

const server = http.createServer((request, response) => {
  if (!isAllowedHost(request.headers.host, allowedHosts)) {
    sendPlain(request, response, 421, "请求主机未获授权。");
    request.resume();
    return;
  }
  if (
    !request.url ||
    !request.url.startsWith("/") ||
    request.url.startsWith("//")
  ) {
    sendPlain(request, response, 400, "请求地址无效。");
    request.resume();
    return;
  }
  if (!["GET", "HEAD", "POST", "PATCH"].includes(request.method ?? "")) {
    sendPlain(request, response, 405, "不支持的请求方法。", {
      Allow: "GET, HEAD, POST, PATCH",
    });
    request.resume();
    return;
  }
  let requestUrl;
  try {
    requestUrl = new URL(
      request.url,
      `http://${request.headers.host}`,
    );
  } catch {
    sendPlain(request, response, 400, "请求地址无效。");
    request.resume();
    return;
  }
  if (
    requestUrl.pathname === "/api/kb" ||
    requestUrl.pathname.startsWith("/api/kb/")
  ) {
    proxyToAgent(request, response, requestUrl);
    return;
  }
  if (serveStatic(request, response, requestUrl.pathname)) {
    return;
  }
  proxyToVinext(request, response);
});

server.headersTimeout = 15_000;
// Large NAS uploads may legitimately take much longer than normal API calls.
// The proxy still enforces the configured byte ceiling while streaming.
server.requestTimeout = upstreamTimeoutMilliseconds + 60_000;
server.keepAliveTimeout = 5_000;
server.maxHeadersCount = 100;

server.listen(publicPort, publicHost, () => {
  console.log(
    `[jingao-web] JAOS 已在 http://${publicHost}:${publicPort} 启动`,
  );
});

function shutdown(signal) {
  server.close(() => {
    if (!vinextProcess.killed) {
      vinextProcess.kill(signal);
    }
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 5_000).unref();
}

vinextProcess.on("exit", (code, signal) => {
  if (code !== 0 && signal === null) {
    console.error(`[jingao-web] 内部页面服务异常退出，代码 ${code}`);
  }
  server.close(() => process.exit(code ?? 1));
});

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
