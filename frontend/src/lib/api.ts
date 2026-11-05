/**
 * Typed fetch wrapper. All calls are same-origin (/api), never external.
 *
 * The access token lives only in memory. On a 401 caused by an expired or revoked access
 * token the client asks /api/auth/refresh once (single-flight, using the httpOnly refresh
 * cookie) and retries the request; if that fails, listeners are told the session ended.
 */

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

/* ---------------------------------------------------------------- session wiring */

let accessToken: string | null = null;
type SessionListener = (event: "expired" | "password_change_required") => void;
const listeners = new Set<SessionListener>();
let refreshHandler: (() => Promise<string | null>) | null = null;
let refreshing: Promise<string | null> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** The auth layer registers how to renew the access token (POST /api/auth/refresh). */
export function setRefreshHandler(handler: (() => Promise<string | null>) | null): void {
  refreshHandler = handler;
}

export function onSessionEvent(listener: SessionListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function emit(event: "expired" | "password_change_required"): void {
  for (const l of listeners) l(event);
}

async function refreshOnce(): Promise<string | null> {
  if (!refreshHandler) return null;
  refreshing ??= refreshHandler().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

const RETRYABLE_401 = new Set(["token_expired", "invalid_token", "session_revoked", "not_authenticated"]);

/* ---------------------------------------------------------------- requests */

export interface RequestOptions {
  body?: unknown;
  signal?: AbortSignal;
  /** Do not attach the bearer token or attempt a refresh (login, refresh, setup). */
  anonymous?: boolean;
}

async function send(method: string, path: string, opts: RequestOptions, token: string | null): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) {
    body = opts.body;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (token && !opts.anonymous) headers.Authorization = `Bearer ${token}`;
  try {
    return await fetch(`/api${path}`, { method, headers, body, signal: opts.signal, credentials: "same-origin" });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "The FabTrack server could not be reached");
  }
}

async function parse<T>(resp: Response): Promise<T> {
  if (resp.status === 204) return undefined as T;
  const body: unknown = await resp.json().catch(() => null);
  if (!resp.ok) {
    if (isApiErrorBody(body)) throw new ApiError(resp.status, body.error.code, body.error.message, body.error.details);
    throw new ApiError(resp.status, "http_error", `Request failed with status ${resp.status}`);
  }
  return body as T;
}

async function sendWithRenewal(method: string, path: string, opts: RequestOptions): Promise<Response> {
  let resp = await send(method, path, opts, accessToken);
  if (resp.status === 401 && !opts.anonymous) {
    const code = await resp
      .clone()
      .json()
      .then((b: unknown) => (isApiErrorBody(b) ? b.error.code : ""))
      .catch(() => "");
    if (RETRYABLE_401.has(code)) {
      const renewed = await refreshOnce();
      if (renewed) {
        resp = await send(method, path, opts, renewed);
      } else {
        emit("expired");
      }
    }
  }
  if (resp.status === 403) {
    const peek = await resp.clone().json().catch(() => null);
    if (isApiErrorBody(peek) && peek.error.code === "password_change_required") emit("password_change_required");
  }
  return resp;
}

export async function apiRequest<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  return parse<T>(await sendWithRenewal(method, path, opts));
}

/** Authenticated binary download (file previews and downloads need the bearer token,
 *  which a plain link cannot send). */
export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const resp = await sendWithRenewal("GET", path, { signal });
  if (!resp.ok) await parse<never>(resp);
  return resp.blob();
}

export const apiGet = <T>(path: string, signal?: AbortSignal) => apiRequest<T>("GET", path, { signal });
export const apiPost = <T>(path: string, body?: unknown, opts: Omit<RequestOptions, "body"> = {}) =>
  apiRequest<T>("POST", path, { ...opts, body });
export const apiPut = <T>(path: string, body?: unknown) => apiRequest<T>("PUT", path, { body });
export const apiPatch = <T>(path: string, body?: unknown) => apiRequest<T>("PATCH", path, { body });
export const apiDelete = <T>(path: string) => apiRequest<T>("DELETE", path);

/** Builds a query string, skipping empty values. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
