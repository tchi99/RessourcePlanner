import { ApiError, SegmentReadModel } from "./api";

export type LoadProfile = "UNIFORM" | "FRONT_LOADED" | "BACK_LOADED" | "BELL";

export type SegmentWrite = {
  demand_number: string;
  start_date: string;
  end_date: string;
  planned_hours: number;
  project_number?: string | null;
  project_name?: string | null;
  technician?: string | null;
  status?: string;
  description?: string;
  source_effort_id?: string | null;
  required_competency?: string | null;
  required_competency_id?: string | null;
  planning_type?: string;
  priority?: string;
  outside_standard_hours?: boolean;
  confirmation?: string | null;
  load_profile?: LoadProfile;
};

export type SegmentUpdateWrite = Partial<SegmentWrite>;

export type SegmentMutationResult = {
  segment_id: string;
  action: string;
  technician?: string | null;
};

type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
  };
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function responseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload | null = null;
  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    // Proxies can return non-JSON errors; keep the HTTP fallback.
  }
  return new ApiError(
    payload?.error?.message || `Erreur HTTP ${response.status}`,
    response.status,
    payload?.error?.code ?? null,
  );
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

async function sendJson<T>(
  path: string,
  method: string,
  body: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...headers,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

export function getSegments(includeCancelled = false, signal?: AbortSignal) {
  const params = new URLSearchParams({ include_cancelled: String(includeCancelled) });
  return getJson<SegmentReadModel[]>(`/api/v1/segments?${params.toString()}`, signal);
}

export function getSegment(segmentId: string, signal?: AbortSignal) {
  return getJson<SegmentReadModel>(`/api/v1/segments/${encodeURIComponent(segmentId)}`, signal);
}

export function createSegment(payload: SegmentWrite, idempotencyKey: string) {
  return sendJson<SegmentMutationResult>(
    "/api/v1/segments",
    "POST",
    payload,
    { "Idempotency-Key": idempotencyKey },
  );
}

export function updateSegment(segmentId: string, payload: SegmentUpdateWrite) {
  return sendJson<SegmentMutationResult>(
    `/api/v1/segments/${encodeURIComponent(segmentId)}`,
    "PATCH",
    payload,
  );
}

export function cancelSegment(segmentId: string) {
  return postJson<SegmentMutationResult>(
    `/api/v1/segments/${encodeURIComponent(segmentId)}/cancel`,
  );
}

export function assignSegment(segmentId: string, technician: string) {
  return sendJson<SegmentMutationResult>(
    `/api/v1/segments/${encodeURIComponent(segmentId)}/assign`,
    "POST",
    { technician },
  );
}
