import { ApiError, ManualAllocationUpdate } from "./api";
import { SegmentMutationResult, SegmentUpdateWrite } from "./segments-api";

export type OverallocationPolicy = "KEEP_EXCEPTION" | "INCREASE_PLANNED";

export type OverallocationContext = {
  segment_id: string;
  planned_hours: number;
  current_planned_hours?: number;
  current_locked_hours?: number;
  projected_locked_hours?: number;
  locked_hours?: number;
  current_excess_hours?: number;
  excess_hours: number;
};

export class OverallocationApiError extends ApiError {
  readonly context: unknown;

  constructor(message: string, status: number, code: string | null, context: unknown) {
    super(message, status, code);
    this.name = "OverallocationApiError";
    this.context = context;
  }
}

type ErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    context?: unknown;
  };
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function errorFromResponse(response: Response) {
  let payload: ErrorPayload | null = null;
  try {
    payload = (await response.json()) as ErrorPayload;
  } catch {
    // Preserve a stable fallback if a proxy returns non-JSON content.
  }
  return new OverallocationApiError(
    payload?.error?.message || `Erreur HTTP ${response.status}`,
    response.status,
    payload?.error?.code ?? null,
    payload?.error?.context ?? null,
  );
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
  if (!response.ok) throw await errorFromResponse(response);
  return response.json() as Promise<T>;
}

export function overallocationContext(reason: unknown): OverallocationContext | null {
  if (!(reason instanceof OverallocationApiError)) return null;
  if (!reason.context || typeof reason.context !== "object") return null;
  const value = reason.context as Record<string, unknown>;
  if (typeof value.segment_id !== "string") return null;
  if (typeof value.planned_hours !== "number") return null;
  if (typeof value.excess_hours !== "number") return null;
  return value as unknown as OverallocationContext;
}

export function createManualAllocationWithOverallocation(
  segmentId: string,
  payload: ManualAllocationUpdate,
  idempotencyKey: string,
  policy: OverallocationPolicy | null = null,
) {
  return sendJson<Record<string, unknown>>(
    `/api/v1/segments/${encodeURIComponent(segmentId)}/allocations`,
    "POST",
    {
      ...payload,
      overallocation_policy: policy,
    },
    { "Idempotency-Key": idempotencyKey },
  );
}

export async function releaseManualAllocation(allocationId: string) {
  const response = await fetch(
    `${API_BASE}/api/v1/allocations/${encodeURIComponent(allocationId)}/release`,
    { method: "POST", headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw await errorFromResponse(response);
  return response.json() as Promise<Record<string, unknown>>;
}

export async function deleteManualAllocation(allocationId: string) {
  const response = await fetch(
    `${API_BASE}/api/v1/allocations/${encodeURIComponent(allocationId)}`,
    { method: "DELETE", headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw await errorFromResponse(response);
  return response.json() as Promise<Record<string, unknown>>;
}

export function updateAllocationWithOverallocation(
  allocationId: string,
  payload: ManualAllocationUpdate,
  policy: OverallocationPolicy | null = null,
) {
  return sendJson<Record<string, unknown>>(
    `/api/v1/allocations/${encodeURIComponent(allocationId)}`,
    "PUT",
    {
      ...payload,
      overallocation_policy: policy,
    },
  );
}

export function updateSegmentWithOverallocation(
  segmentId: string,
  payload: SegmentUpdateWrite,
  allowLockedOverallocation: boolean,
) {
  return sendJson<SegmentMutationResult>(
    `/api/v1/segments/${encodeURIComponent(segmentId)}`,
    "PATCH",
    {
      ...payload,
      allow_locked_overallocation: allowLockedOverallocation,
    },
  );
}
