/** Proxy de transporte same-origin; las reglas y la autorización pertenecen a FastAPI. */
export const runtime = "nodejs";

async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const url = new URL(
    `/api/v1/${path.map(encodeURIComponent).join("/")}`,
    base,
  );
  url.search = new URL(request.url).search;
  const headers = new Headers();
  for (const name of [
    "content-type",
    "cookie",
    "origin",
    "x-csrf-token",
    "x-correlation-id",
    "idempotency-key",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // CSV (…/imports) y Excel (…/imports/xlsx y …/imports/xlsx/inspect, Fase 12A).
  const isCsvUpload =
    request.method === "POST" &&
    path[0] === "projects" &&
    path[2] === "imports" &&
    (path.length === 3 ||
      (path[3] === "xlsx" &&
        (path.length === 4 || (path.length === 5 && path[4] === "inspect"))));
  const isSemanticSave =
    request.method === "POST" &&
    path.length === 3 &&
    path[0] === "representations" &&
    path[2] === "semantic-contracts";
  const maximumBody = isCsvUpload
    ? 5 * 1024 * 1024
    : isSemanticSave
      ? 2 * 1024 * 1024
      : 65536;
  let body: Uint8Array | undefined;
  if (!["GET", "HEAD"].includes(request.method) && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let length = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      length += chunk.value.byteLength;
      if (length > maximumBody) {
        await reader.cancel();
        return Response.json(
          {
            code: "BODY_TOO_LARGE",
            message: "La solicitud excede el límite permitido.",
          },
          { status: 413 },
        );
      }
      chunks.push(chunk.value);
    }
    body = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.byteLength;
    }
  }
  try {
    const upstream = await fetch(url, {
      method: request.method,
      headers,
      body: body as BodyInit | undefined,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15000)]),
    });
    const outgoing = new Headers({ "cache-control": "no-store" });
    for (const name of [
      "content-type",
      "x-correlation-id",
      "x-content-type-options",
      "content-disposition",
    ]) {
      const value = upstream.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      outgoing.append("set-cookie", cookie);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      {
        code: "API_UNAVAILABLE",
        message:
          "No pudimos conectar con la API. Comprueba que el backend está ejecutándose.",
      },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH };
