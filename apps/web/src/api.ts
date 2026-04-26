export const apiBaseUrl = import.meta.env.VITE_STRUCTURA_API_BASE_URL ?? "";

let configuredCsrfCookieName = "structura_csrf";

export function configureSecurityCookieNames(config: {
  csrfCookieName?: string | null;
}): void {
  if (config.csrfCookieName?.trim()) {
    configuredCsrfCookieName = config.csrfCookieName.trim();
  }
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

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}
