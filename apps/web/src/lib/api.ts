/**
 * Calls to the AaharOS API on the same origin (Vite proxies /api). Auth lives in httpOnly cookies, so JavaScript
 * never sees a token. A 401 triggers one refresh attempt, then the error is passed on (the page offers sign-in).
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  return fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } }).error;
    throw new ApiError(
      res.status,
      err?.code ?? "error",
      err?.message ?? `request failed (${res.status})`,
    );
  }
  return data as T;
}

let refreshing: Promise<boolean> | null = null;

/**
 * Refresh the session once for everyone who needs it (single flight). Refresh tokens rotate and a reused one revokes
 * the session (ADR-0010), so two parallel refreshes from the same tab would sign the user out.
 */
export function refreshSession(): Promise<boolean> {
  refreshing ??= send("POST", "/api/auth/refresh")
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res = await send(method, path, body);
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    if (await refreshSession()) res = await send(method, path, body);
  }
  return parse<T>(res);
}

export const apiGet = <T>(path: string) => api<T>("GET", path);
export const apiPost = <T>(path: string, body?: unknown) => api<T>("POST", path, body);
