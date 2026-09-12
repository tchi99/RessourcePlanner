export type ProjectReadModel = {
  id: string;
  number: string;
  name: string;
  client: string | null;
  project_manager: string | null;
  status: string;
  erp_external_id: string | null;
};

export type WorkPackageReadModel = {
  id: string;
  reference: string;
  project_number: string;
  code: string | null;
  name: string;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  planned_hours: number | null;
  status: string;
};

export type WorkPackageWrite = {
  project_number: string;
  code: string | null;
  name: string;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  planned_hours: number | null;
  status: string;
};

export type WorkPackageMutationResult = {
  reference: string;
  action: string;
};

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
  request_type: string | null;
  priority: string | null;
  confirmation: string | null;
  desired_start: string | null;
  desired_end: string | null;
  description: string | null;
  site_client: string | null;
  location: string | null;
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
  kind: "CUMULATIVE" | "ALTERNATIVE";
  start_date: string;
  end_date: string;
  hours: number;
  confirmation: "Tentative" | "Confirmée";
  alternative_group: string | null;
  proposed_resource: string | null;
  resource_count: number;
  note: string | null;
  selected: boolean;
};

export type DemandPeriodWrite = {
  period_id: string;
  start_date: string;
  end_date: string;
  hours: number;
  kind: "CUMULATIVE" | "ALTERNATIVE";
  alternative_group: string | null;
  confirmation: "Tentative" | "Confirmée";
  proposed_resource: string | null;
  resource_count: number;
  note: string;
};

export type DemandPeriodsMutationResult = {
  demand_number: string;
  period_count: number;
  status: string | null;
  reapproval_required: boolean;
};

export type DemandAlternativeSelectionResult = {
  demand_number: string;
  alternative_group: string;
  period_id: string;
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

export type MediumTermCapacityBucketReadModel = {
  week_start: string;
  week_end: string;
  resource_class: string | null;
  resource_count: number;
  capacity_hours: number;
  firm_hours: number;
  current_potential_hours: number;
  submitted_hours: number;
  replacement_proposal_hours: number;
  replacement_delta_hours: number;
  exposure_hours: number;
  firm_residual_hours: number;
  residual_hours: number;
  utilization_pct: number | null;
  state: "available" | "warning" | "overloaded" | "unavailable";
};

export type PlanningSnapshotReadModel = {
  start: string;
  end: string;
  resources: ResourceReadModel[];
  demands: DemandReadModel[];
  segments: SegmentReadModel[];
  shifts: ShiftReadModel[];
  pending_loads: PendingDemandLoadReadModel[];
  capacity_buckets: MediumTermCapacityBucketReadModel[];
  firm_hours: number;
  potential_hours: number;
  replacement_proposal_hours: number;
};

export type DemandWrite = {
  project_number: string;
  project_name?: string;
  client?: string;
  requester: string | null;
  work_package_ref: string | null;
  request_type?: string;
  priority: string;
  confirmation: "Tentative" | "Confirmée";
  desired_start: string;
  desired_end: string | null;
  description: string;
  resource_count: number;
  required_competencies: string | null;
  estimated_hours: number | null;
  estimated_days: number | null;
  proposed_technician: string | null;
};

export type DemandMutationResult = {
  demand_number: string;
  status: string | null;
  reapproval_required: boolean;
};

export type ManualAllocationUpdate = {
  technician: string;
  day: string;
  hours: number;
  outside_standard_hours: boolean;
  note: string;
  confirmation: string | null;
};

export type QuickShiftCreate = {
  project_number: string;
  technician: string;
  day: string;
  hours: number;
  project_name: string;
  outside_standard_hours: boolean;
  note: string;
  description: string;
  confirmation: "Tentative" | "Confirmée";
};

export type QuickShiftCreated = {
  segment_id: string;
  allocation_id: string;
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

export function getPlanningSnapshot(start: string, end: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ start, end });
  return getJson<PlanningSnapshotReadModel>(`/api/v1/planning/snapshot?${params.toString()}`, signal);
}

export function getProjects(activeOnly = true, signal?: AbortSignal) {
  const params = new URLSearchParams({ active_only: String(activeOnly) });
  return getJson<ProjectReadModel[]>(`/api/v1/projects?${params.toString()}`, signal);
}

export function getWorkPackages(projectNumber: string, activeOnly = true, signal?: AbortSignal) {
  const params = new URLSearchParams({
    project_number: projectNumber,
    active_only: String(activeOnly),
  });
  return getJson<WorkPackageReadModel[]>(`/api/v1/work-packages?${params.toString()}`, signal);
}

export function createWorkPackage(payload: WorkPackageWrite, idempotencyKey: string) {
  return sendJson<WorkPackageMutationResult>(
    "/api/v1/work-packages",
    "POST",
    payload,
    { "Idempotency-Key": idempotencyKey },
  );
}

export function updateWorkPackage(reference: string, payload: WorkPackageWrite) {
  return sendJson<WorkPackageMutationResult>(
    `/api/v1/work-packages/${encodeURIComponent(reference)}`,
    "PATCH",
    payload,
  );
}

export function getResources(activeOnly = true, signal?: AbortSignal) {
  const params = new URLSearchParams({ active_only: String(activeOnly) });
  return getJson<ResourceReadModel[]>(`/api/v1/resources?${params.toString()}`, signal);
}

export function getDemands(signal?: AbortSignal) {
  return getJson<DemandReadModel[]>("/api/v1/demands", signal);
}

export function getDemand(number: string, signal?: AbortSignal) {
  return getJson<DemandReadModel>(`/api/v1/demands/${encodeURIComponent(number)}`, signal);
}

export function getDemandPeriods(number: string, signal?: AbortSignal) {
  return getJson<DemandPeriodReadModel[]>(
    `/api/v1/demands/${encodeURIComponent(number)}/periods`,
    signal,
  );
}

export function createDemand(payload: DemandWrite, idempotencyKey: string) {
  return sendJson<DemandMutationResult>(
    "/api/v1/demands",
    "POST",
    { ...payload, submit: false },
    { "Idempotency-Key": idempotencyKey },
  );
}

export function updateDemand(number: string, payload: DemandWrite, comment: string) {
  // request_type is not edited in tranche 3A. Do not write a fallback value back over
  // historical requests until the field has an explicit UI and canonical SQL read.
  const { request_type: _requestType, ...editablePayload } = payload;
  return sendJson<DemandMutationResult>(
    `/api/v1/demands/${encodeURIComponent(number)}`,
    "PATCH",
    { ...editablePayload, comment },
  );
}

export function replaceDemandPeriods(number: string, periods: DemandPeriodWrite[]) {
  return sendJson<DemandPeriodsMutationResult>(
    `/api/v1/demands/${encodeURIComponent(number)}/periods`,
    "PUT",
    { periods },
  );
}

export function selectDemandAlternative(
  number: string,
  alternativeGroup: string,
  periodId: string,
) {
  return sendJson<DemandAlternativeSelectionResult>(
    `/api/v1/demands/${encodeURIComponent(number)}/alternative-groups/${encodeURIComponent(alternativeGroup)}/selection`,
    "PUT",
    { period_id: periodId },
  );
}

export function updateAllocation(allocationId: string, payload: ManualAllocationUpdate) {
  return sendJson<Record<string, unknown>>(
    `/api/v1/allocations/${encodeURIComponent(allocationId)}`,
    "PUT",
    payload,
  );
}

export function createQuickShift(payload: QuickShiftCreate, idempotencyKey: string) {
  return sendJson<QuickShiftCreated>(
    "/api/v1/quick-shifts",
    "POST",
    payload,
    { "Idempotency-Key": idempotencyKey },
  );
}