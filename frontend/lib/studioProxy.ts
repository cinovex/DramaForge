const studioServer = "http://127.0.0.1:3001";

export async function proxyStudioRequest(request: Request, namespace: "api" | "mcp" | "a2a", path: string[]) {
  const incomingUrl = new URL(request.url);
  const source = request.headers.get("origin") ?? request.headers.get("referer");
  if (!source) return new Response("Forbidden", { status: 403 });

  try {
    if (new URL(source).origin !== incomingUrl.origin) return new Response("Forbidden", { status: 403 });
  } catch {
    return new Response("Forbidden", { status: 403 });
  }

  const isSharedSettingsRoute = namespace === "api" && path[0] === "settings"
    && ((path.length === 2 && path[1] === "get" && request.method === "GET")
      || (path.length === 2 && path[1] === "save" && request.method === "PUT"));
  const upstreamBase = isSharedSettingsRoute ? "http://127.0.0.1:8000" : studioServer;
  const upstreamUrl = new URL(`/${namespace}/${path.map(encodeURIComponent).join("/")}${incomingUrl.search}`, upstreamBase);
  const headers = new Headers(request.headers);
  for (const name of ["connection", "content-length", "host", "origin", "referer", "transfer-encoding"]) headers.delete(name);
  headers.set("origin", studioServer);
  headers.set("referer", `${studioServer}/canvasApp/index.html`);

  const hasBody = !["GET", "HEAD"].includes(request.method) && request.body !== null;
  const init = {
    method: request.method,
    headers,
    cache: "no-store" as const,
    redirect: "manual" as const,
    ...(hasBody ? { body: request.body, duplex: "half" as const } : {}),
  } as RequestInit & { duplex?: "half" };

  try {
    const upstream = await fetch(upstreamUrl, init);
    const responseHeaders = new Headers(upstream.headers);
    for (const name of ["connection", "transfer-encoding"]) responseHeaders.delete(name);

    const contentType = responseHeaders.get("content-type") ?? "";
    // Range reads intentionally return partial JSON (206). Re-parsing those
    // bytes as a complete JSON document fails and turns a valid partial read
    // into a 502, which prevents Toonflow from recognizing canvas files.
    if (namespace === "api" && upstream.ok && upstream.status !== 206 && !responseHeaders.has("content-range")
      && request.method !== "HEAD" && contentType.includes("application/json")) {
      const payload: unknown = await upstream.json();
      rewriteApiLinks(payload);
      responseHeaders.delete("content-length");
      responseHeaders.delete("content-encoding");
      return new Response(JSON.stringify(payload), { status: upstream.status, statusText: upstream.statusText, headers: responseHeaders });
    }

    if (namespace === "api" && upstream.ok && request.method !== "HEAD" && /(?:javascript|ecmascript)/i.test(contentType)) {
      const source = await upstream.text();
      const integratedSource = source.replace(/(["'`])\/(api|mcp|a2a)\//g, "$1/studio-$2/");
      responseHeaders.delete("content-length");
      responseHeaders.delete("content-encoding");
      return new Response(integratedSource, { status: upstream.status, statusText: upstream.statusText, headers: responseHeaders });
    }

    return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: responseHeaders });
  } catch {
    return new Response("Integrated studio service is unavailable", { status: 502 });
  }
}

function rewriteApiLinks(value: unknown): void {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    for (const item of value) rewriteApiLinks(item);
    return;
  }
  const record = value as Record<string, unknown>;
  for (const [key, item] of Object.entries(record)) {
    if (key === "url" && typeof item === "string" && /^\/(?:api|mcp|a2a)\//.test(item)) {
      record[key] = item.replace(/^\/(api|mcp|a2a)\//, "/studio-$1/");
    } else {
      rewriteApiLinks(item);
    }
  }
}
