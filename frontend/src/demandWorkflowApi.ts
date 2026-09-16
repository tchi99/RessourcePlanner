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

type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
  };
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function workflowPost(
  number: string,
  action: "submit" | "approve" | "emergency-plan" | "correction" | "cancel",
  body?: { comment: string },
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

  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      // Keep the stable fallback when an intermediary returns non-JSON content.
    }
    throw new ApiError(
      payload?.error?.message || `Erreur HTTP ${response.status}`,
      response.status,
      payload?.error?.code ?? null,
    );
  }

  return response.json() as Promise<DemandWorkflowResult>;
}

export function submitDemand(number: string) {
  return workflowPost(number, "submit");
}

export function approveDemand(number: string, comment: string) {
  return workflowPost(number, "approve", { comment });
}

export function emergencyPlanDemand(number: string, comment: string) {
  return workflowPost(number, "emergency-plan", { comment });
}

export function requestDemandCorrection(number: string, comment: string) {
  return workflowPost(number, "correction", { comment });
}

export function cancelDemand(number: string) {
  return workflowPost(number, "cancel");
}