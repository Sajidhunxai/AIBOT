function getApiBase(): string {
  // Browser: same-origin proxy via next.config.js rewrites (avoids CORS).
  if (typeof window !== "undefined") {
    return "";
  }
  // Server-side render: talk to API directly.
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

const FETCH_TIMEOUT_MS = 20_000;

function fetchWithTimeout(input: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  return fetch(input, { ...init, signal: controller.signal }).finally(() => clearTimeout(timer));
}

export async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetchWithTimeout(`${getApiBase()}/api/v1${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function postApi<T>(path: string, body?: object): Promise<T> {
  const res = await fetchWithTimeout(`${getApiBase()}/api/v1${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = typeof err.detail === "string" ? err.detail : `API error: ${res.status}`;
    throw new Error(detail);
  }
  return res.json();
}

export async function putApi<T>(path: string, body: object): Promise<T> {
  const res = await fetchWithTimeout(`${getApiBase()}/api/v1${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = typeof err.detail === "string" ? err.detail : `API error: ${res.status}`;
    throw new Error(detail);
  }
  return res.json();
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
