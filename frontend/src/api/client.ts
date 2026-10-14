// Thin fetch wrapper. All calls go through /api (Vite proxy in dev, nginx in Docker).

export const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** FastAPI errors: {detail: "text"} or {detail: [{loc, msg}, ...]} for validation. */
export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map((e) => {
          if (e && typeof e === "object" && "msg" in e) {
            const loc = Array.isArray((e as { loc?: unknown }).loc)
              ? ((e as { loc: unknown[] }).loc.filter((p) => p !== "body").join("."))
              : "";
            return loc ? `${loc}: ${(e as { msg: string }).msg}` : (e as { msg: string }).msg;
          }
          return String(e);
        })
        .join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "network");
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, `HTTP ${res.status}`));
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, json?: unknown) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: json === undefined ? undefined : JSON.stringify(json),
    }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
};

export function qs(params: Record<string, string | number | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}

export type ExportKind = "stats" | "draws" | "combos" | "bao";
export type ExportFormat = "csv" | "xlsx";

/** Export endpoint path. stats/draws/bao are GETs whose query carries the on-screen parameters. */
export function exportUrl(
  game: string,
  kind: ExportKind,
  format: ExportFormat,
  query?: Record<string, string | number | undefined | null>,
): string {
  return `${API_BASE}/games/${encodeURIComponent(game)}/export/${kind}.${format}${query ? qs(query) : ""}`;
}

/** File name from a Content-Disposition header (RFC 6266 filename* wins over filename). */
export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      /* fall through to the plain filename */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : fallback;
}

/**
 * Fetches a file and hands it to the browser as a download. Going through fetch (rather than a
 * plain link) lets a 409 "no draws stored" show up as a message instead of a saved error file.
 */
export async function downloadFile(url: string, init?: RequestInit, fallbackName = "export"): Promise<void> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError(0, "network");
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    throw new ApiError(res.status, errorMessage(body, `HTTP ${res.status}`));
  }
  const blob = await res.blob();
  const name = filenameFromDisposition(res.headers.get("Content-Disposition"), fallbackName);
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}
