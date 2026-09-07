import {sessionRequestScope} from "./sessionRequests";

export const apiBaseUrl = import.meta.env.VITE_STRUCTURA_API_BASE_URL ?? "";

let configuredCsrfCookieName = "structura_csrf";

export function configureSecurityCookieNames(config: {
  csrfCookieName?: string | null;
}): void {
  configuredCsrfCookieName = config.csrfCookieName?.trim() || "structura_csrf";
}

export function csrfToken(): string {
  const cookie = document.cookie
    .split("; ")
    .find((part) => part.split("=")[0] === configuredCsrfCookieName);
  return cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : "";
}

export function assetUrl(path?: string): string | undefined {
  if (!path) {
    return undefined;
  }
  return path.startsWith("http") ? path : `${apiBaseUrl}${path}`;
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const scope = sessionRequestScope(init?.signal);
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: "include",
    ...init,
    signal: scope.signal,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
  scope.assertCurrent();
  if (!response.ok) {
    let detail: unknown;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body) detail = body.detail;
    } catch {
      // Proxy/network responses may not contain the API's safe JSON error shape.
    }
    scope.assertCurrent();
    // Sign-in failures and session checks are handled by the auth boundary.
    if (response.status === 401 && path !== "/api/v1/auth/session") scope.unauthorized();
    throw new ApiError(response.status, typeof detail === "string" && detail
      ? detail : `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json() as T;
  scope.assertCurrent();
  return body;
}
