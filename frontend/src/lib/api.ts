/** Minimal typed fetch wrapper. All API calls are same-origin (/api), never external. */

export interface ApiErrorBody {
  error: { code: string; message: string; details: unknown };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const err = (value as { error: unknown }).error;
  return typeof err === "object" && err !== null && "code" in err && "message" in err;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`/api${path}`, { headers: { Accept: "application/json" }, signal });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "The FabTrack server could not be reached");
  }
  const body: unknown = await resp.json().catch(() => null);
  if (!resp.ok) {
    if (isApiErrorBody(body)) {
      throw new ApiError(resp.status, body.error.code, body.error.message, body.error.details);
    }
    throw new ApiError(resp.status, "http_error", `Request failed with status ${resp.status}`);
  }
  return body as T;
}
