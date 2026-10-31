import { createClient, type paths } from "@dataflow/api-client";

let csrfToken: string | null = null;
export function setCsrfToken(value: string | null) {
  csrfToken = value;
}
export const api = createClient<paths>({
  baseUrl: "",
  credentials: "same-origin",
});
api.use({
  onRequest({ request }) {
    if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(request.method))
      request.headers.set("x-csrf-token", csrfToken);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && csrfToken) {
      csrfToken = null;
      window.dispatchEvent(new Event("dataflow:session-expired"));
    }
    return response;
  },
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly correlationId?: string,
  ) {
    super(message);
  }
}
export function requireData<T>({
  data,
  error,
  response,
}: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (!response.ok || data === undefined) {
    const message =
      error &&
      typeof error === "object" &&
      "message" in error &&
      typeof error.message === "string"
        ? error.message
        : "No se pudo completar la operación.";
    throw new ApiError(
      message,
      response.status,
      response.headers.get("x-correlation-id") ?? undefined,
    );
  }
  return data;
}
export function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "No pudimos conectar con la API. Comprueba que el backend está ejecutándose.";
}
