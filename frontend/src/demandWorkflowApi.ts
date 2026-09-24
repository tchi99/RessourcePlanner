import { ApiError } from "./api";

export type PlanningResult = {
  segments: number;
  allocations: number;
  locked_allocations: number;
  requested_hours: number;
  allocated_hours: number;
  overtime_hours: number;
  unallocated_hours: number;
  engine: string;
};

export type DemandWorkflowResult = {
  demand_number: string;
  status: string | null;
  reapproval_required: boolean;
  planning: PlanningResult | null;
};

export type DemandCancellationMutationResult = {
  demand_number: string;
  status: string;
  cancellation_request_id: string;
  cancellation_state: "PENDING" | "REJECTED";
};

export type DemandCancellationPolicyState = {
  has_operational_decisions: boolean;
  direct_cancel: boolean;
  request_cancellation: boolean;
  cancellation_pending: boolean;
  resolve_cancellation: boolean;
  reason_code: string | null;
  reason: string | null;
};

export type WorkflowAction =
  | "modify"
  | "submit"
  | "approve"
  | "emergency-plan"
  | "correction"
  | "cancel"
  | "request-cancellation"
  | "reject-cancellation";

export type DemandWorkflowActionState = {
  action: WorkflowAction;
  allowed: boolean;
  required_permission: string;
  required_permissions?: string[];
  reason_code: string | null;
  reason: string | null;
};

export type DemandWorkflowState = {
  demand_number: string;
  status: string;
  version: number;
  available_actions: WorkflowAction[];
  actions: DemandWorkflowActionState[];
  cancellation?: DemandCancellationPolicyState | null;
};

type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
  };
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function apiError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload | null = null;
  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    // Keep the stable fallback when an intermediary returns non-JSON content.
  }
  return new ApiError(
    payload?.error?.message || `Erreur HTTP ${response.status}`,
    response.status,
    payload?.error?.code ?? null,
  );
}

export async function getDemandWorkflowState(
  number: string,
): Promise<DemandWorkflowState> {
  const response = await fetch(
    `${API_BASE}/api/v1/demands/${encodeURIComponent(number)}/workflow-actions`,
    {
      headers: { Accept: "application/json" },
    },
  );
  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<DemandWorkflowState>;
}

async function workflowPost(
  number: string,
  action: Exclude<WorkflowAction, "modify">,
  body?: { comment?: string; expected_version?: number },
): Promise<DemandWorkflowResult> {
  const response = await fetch(
    `${API_BASE}/api/v1/demands/${encodeURIComponent(number)}/${action}`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    },
  );

  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<DemandWorkflowResult>;
}

function versionBody(expectedVersion?: number) {
  return expectedVersion === undefined ? undefined : { expected_version: expectedVersion };
}

export function submitDemand(number: string, expectedVersion?: number) {
  return workflowPost(number, "submit", versionBody(expectedVersion));
}

export function approveDemand(
  number: string,
  comment: string,
  expectedVersion?: number,
) {
  return workflowPost(number, "approve", {
    comment,
    ...(expectedVersion === undefined ? {} : { expected_version: expectedVersion }),
  });
}

export function emergencyPlanDemand(
  number: string,
  comment: string,
  expectedVersion?: number,
) {
  return workflowPost(number, "emergency-plan", {
    comment,
    ...(expectedVersion === undefined ? {} : { expected_version: expectedVersion }),
  });
}

export function requestDemandCorrection(
  number: string,
  comment: string,
  expectedVersion?: number,
) {
  return workflowPost(number, "correction", {
    comment,
    ...(expectedVersion === undefined ? {} : { expected_version: expectedVersion }),
  });
}

export function cancelDemand(number: string, expectedVersion?: number) {
  return workflowPost(number, "cancel", versionBody(expectedVersion));
}

export async function requestDemandCancellation(
  number: string,
  reason: string,
  expectedVersion: number,
): Promise<DemandCancellationMutationResult> {
  const response = await fetch(
    `${API_BASE}/api/v1/demands/${encodeURIComponent(number)}/request-cancellation`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ reason, expected_version: expectedVersion }),
    },
  );
  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<DemandCancellationMutationResult>;
}

export async function rejectDemandCancellation(
  number: string,
  cancellationRequestId: string,
  comment: string,
  expectedVersion: number,
): Promise<DemandCancellationMutationResult> {
  const response = await fetch(
    `${API_BASE}/api/v1/demands/${encodeURIComponent(number)}/reject-cancellation`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        cancellation_request_id: cancellationRequestId,
        comment,
        expected_version: expectedVersion,
      }),
    },
  );
  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<DemandCancellationMutationResult>;
}
