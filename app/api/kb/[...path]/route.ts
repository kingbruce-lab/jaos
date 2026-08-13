const DEFAULT_AGENT_URL = "http://127.0.0.1:8000";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxy(request: Request, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const baseUrl = (process.env.JINGAO_AGENT_URL || DEFAULT_AGENT_URL).replace(/\/+$/, "");
  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL(`${baseUrl}/${path.join("/")}`);
  upstreamUrl.search = incomingUrl.search;

  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  const contentType = request.headers.get("content-type");
  const contentLength = request.headers.get("content-length");
  const range = request.headers.get("range");
  const ifRange = request.headers.get("if-range");
  if (authorization) headers.set("authorization", authorization);
  if (contentType) headers.set("content-type", contentType);
  if (contentLength) headers.set("content-length", contentLength);
  if (range) headers.set("range", range);
  if (ifRange) headers.set("if-range", ifRange);

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : request.body;

  try {
    const requestInit: RequestInit & { duplex?: "half" } = {
      method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
    };
    if (body) requestInit.duplex = "half";
    const upstream = await fetch(upstreamUrl, requestInit);
    const responseHeaders = new Headers();
    for (const name of [
      "content-type",
      "content-disposition",
      "content-length",
      "accept-ranges",
      "content-range",
      "etag",
      "last-modified",
      "retry-after",
      "x-content-type-options",
    ]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    responseHeaders.set("cache-control", "no-store");
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { detail: "知识服务暂未启动，请联系管理员。" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
