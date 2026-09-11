export type ResourceReadModel = {
  id: string;
  name: string;
  resource_class: string | null;
  competencies: string | null;
  note: string | null;
  active: boolean;
  sort_order: number;
  external_id: string | null;
};

export type DemandReadModel = {
  number: string;
  status: string;
  project_number: string | null;
  project_name: string | null;
  client: string | null;
  project_manager: string | null;
  requester: string | null;
  priority: string | null;
  confirmation: string | null;
  desired_start: string | null;
  desired_end: string | null;
  description: string | null;
  work_package_ref: string | null;
  work_package_name: string | null;
  resource_count: number;
  required_competencies: string | null;
  estimated_hours: number | null;
  estimated_days: number | null;
  proposed_resource: string | null;
};

export type SegmentReadModel = {
  segment_id: string;
  demand_number: string | null;
  project_number: string | null;
  project_name: string | null;
  resource_name: string | null;
  start_date: string | null;
  end_date: string | null;
  planned_hours: number;
  status: string;
  description: string | null;
  origin: string | null;
  required_competency: string | null;
  planning_type: string | null;
  priority: string | null;
  outside_standard_hours: boolean;
  confirmation: string | null;
  confirmation_overridden: boolean;
  project_manager: string | null;
  requester: string | null;
};

export type ShiftReadModel = {
  allocation_id: string;
  segment_id: string;
  resource_id: string;
  resource_name: string;
  work_date: string;
  hours: number;
  allocation_type: string | null;
  source: string;
  locked: boolean;
  outside_standard_hours: boolean;
  confirmation: string | null;
  confirmation_override: string | null;
  load_kind: string;
  note: string | null;
  demand_number: string | null;
  project_number: string | null;
  project_name: string | null;
  project_manager: string | null;
  requester: string | null;
};

export type DemandPeriodReadModel = {
  period_id: string;
  demand_number: string;
  sequence: number;
  kind: string;
  start_date: string;
  end_date: string;
  hours: number;
  confirmation: string;
  alternative_group: string | null;
  proposed_resource: string | null;
  resource_count: number;
  note: string | null;
  selected: boolean;
};

export type PendingDemandLoadReadModel = {
  demand_number: string;
  project_number: string | null;
  project_name: string | null;
  start_date: string;
  end_date: string;
  projected_hours: number | null;
  window_hours: number;
  mode: string;
  load_kind: string;
  current_plan_hours: number;
  delta_hours: number | null;
  resource_count: number;
  required_competencies: string | null;
  proposed_resource: string | null;
  work_package_ref: string | null;
  confirmation: string | null;
  periods: DemandPeriodReadModel[];
};

export type PlanningSnapshotReadModel = {
  start: string;
  end: string;
  resources: ResourceReadModel[];
  demands: DemandReadModel[];
  segments: SegmentReadModel[];
  shifts: ShiftReadModel[];
  pending_loads: PendingDemandLoadReadModel[];
  firm_hours: number;
  potential_hours: number;
  replacement_proposal_hours: number;
};

export type ManualAllocationUpdate = {
  technician: string;
  day: string;
  hours: number;
  outside_standard_hours: boolean;
  note: string;
  confirmation: string | null;
};

type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    context?: unknown;
  };
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function responseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload | null = null;
  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    // Keep the stable fallback below when a proxy/server returns non-JSON content.
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

async function sendJson<T>(path: string, method: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

export function getPlanningSnapshot(start: string, end: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ start, end });
  return getJson<PlanningSnapshotReadModel>(`/api/v1/planning/snapshot?${params.toString()}`, signal);
}

export function updateAllocation(allocationId: string, payload: ManualAllocationUpdate) {
  return sendJson<Record<string, unknown>>(
    `/api/v1/allocations/${encodeURIComponent(allocationId)}`,
    "PUT",
    payload,
  );
}
