/**
 * Thin API client: bearer token, JSON, the backend's error envelope, file downloads.
 */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "pec.token";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Human-readable list of server-side validation messages, if any. */
  get lines(): string[] {
    const errs = this.details?.errors;
    if (Array.isArray(errs)) {
      return errs.map((e) => (typeof e === "string" ? e : `${(e as { loc?: string[] }).loc?.slice(1).join(".")}: ${(e as { msg?: string }).msg}`));
    }
    return [];
  }
}

export const tokenStore = {
  get: (): string | null => (typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY)),
  set: (t: string) => window.localStorage.setItem(TOKEN_KEY, t),
  clear: () => window.localStorage.removeItem(TOKEN_KEY),
};

type Query = Record<string, string | number | boolean | undefined | null | (string | number)[]>;

export function qs(params?: Query): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.append(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${API_URL}${path}${qs(query)}`, { method, headers, body: payload });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = data?.error || {};
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
      tokenStore.clear();
      window.location.href = "/login";
    }
    throw new ApiError(res.status, err.code || "HTTP_ERROR", err.message || res.statusText, err.details || {});
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, form),

  /** Download a file (CSV/XLSX/attachment) with the bearer token. */
  async download(path: string, query?: Query, fallbackName = "export"): Promise<void> {
    const res = await fetch(`${API_URL}${path}${qs(query)}`, { headers: { Authorization: `Bearer ${tokenStore.get() ?? ""}` } });
    if (!res.ok) throw new ApiError(res.status, "DOWNLOAD_FAILED", "Download failed");
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const name = /filename="?([^"]+)"?/.exec(cd)?.[1] || fallbackName;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  },
};
