/**
 * Base same-origin (proxy `rewrites` de next.config.ts) — jamais d'appel direct
 * au backend depuis le navigateur (plan.md § 3.8, cookie httpOnly + zéro CORS).
 */
const API_BASE = "/api/backend/v1";

/**
 * Format d'erreur unique, produit par les exception handlers globaux du backend
 * (plan.md § 3.5) — absent d'`openapi.json` car il n'est pas porté par un
 * `response_model` Pydantic, donc pas généré dans `schema.d.ts` : type à la main ici,
 * un seul endroit.
 */
interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
  };
}

export type ApiErrorCode =
  | "validation_error"
  | "unauthenticated"
  | "forbidden_role"
  | "not_found"
  | "duplicate_exact"
  | "duplicate_probable"
  | "invalid_transition"
  | "siret_invalid"
  | "siret_not_found"
  | "siret_lookup_unavailable"
  | "conflict"
  | "inspection_not_allowed"
  | "inspection_incomplete"
  | "photo_quota_exceeded"
  | "internal_error"
  | (string & {});

/** Erreur typée dérivée du format d'erreur unique du backend (plan.md § 3.5). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly details: Record<string, unknown> | null;

  constructor(
    status: number,
    code: ApiErrorCode,
    message: string,
    details: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Vrai si l'utilisateur n'est pas (ou plus) authentifié. */
  get isUnauthenticated(): boolean {
    return this.status === 401 || this.code === "unauthenticated";
  }
}

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: Json;
  /** Ne pas rejeter en ApiError sur ces statuts (ex: 404 attendu comme résultat métier). */
  toleratedStatuses?: number[];
}

/**
 * Client typé enveloppant `fetch`. Envoie/reçoit toujours du JSON `snake_case`
 * (§ 3.5) et convertit toute réponse d'erreur en `ApiError`. Le cookie de
 * session est same-origin : `credentials: "same-origin"` suffit, aucun header
 * d'autorisation à poser manuellement.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { body, headers, toleratedStatuses = [], ...rest } = options;
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  let res: Response;
  try {
    res = await fetch(url, {
      ...rest,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "internal_error", "Impossible de contacter le serveur. Vérifiez votre connexion.");
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await res.json().catch(() => null) : null;

  if (!res.ok && !toleratedStatuses.includes(res.status)) {
    if (payload && typeof payload === "object" && "error" in (payload as Record<string, unknown>)) {
      const errBody = (payload as ApiErrorBody).error;
      throw new ApiError(res.status, errBody.code, errBody.message, errBody.details ?? null);
    }
    throw new ApiError(res.status, "internal_error", `Erreur inattendue du serveur (${res.status}).`);
  }

  return payload as T;
}

/**
 * Upload `multipart/form-data` (photos, plan.md § 6 J2 : `POST /vehicles/{id}/photos`) —
 * jamais de `JSON.stringify`/`Content-Type` posé à la main, le navigateur fixe la
 * boundary. Même conversion d'erreur qu'`apiFetch` (format unique § 3.5).
 */
export async function apiUpload<T = unknown>(path: string, formData: FormData): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      body: formData,
    });
  } catch {
    throw new ApiError(0, "internal_error", "Impossible de contacter le serveur. Vérifiez votre connexion.");
  }

  const contentType = res.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    if (payload && typeof payload === "object" && "error" in (payload as Record<string, unknown>)) {
      const errBody = (payload as ApiErrorBody).error;
      throw new ApiError(res.status, errBody.code, errBody.message, errBody.details ?? null);
    }
    throw new ApiError(res.status, "internal_error", `Erreur inattendue du serveur (${res.status}).`);
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: ApiFetchOptions) => apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: Json, options?: ApiFetchOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: Json, options?: ApiFetchOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: Json, options?: ApiFetchOptions) =>
    apiFetch<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: ApiFetchOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
  upload: apiUpload,
};
