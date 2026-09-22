import { ApiError } from "./api";

export type PlanDeltaChange = "ADD" | "MODIFY" | "MOVE" | "CANCEL";

export type DemandPlanDeltaItem = {
  change: PlanDeltaChange;
  segment_id: string;
  current_resource_name: string | null;
  proposed_resource_name: string | null;
  current_resource_id: string | null;
  proposed_resource_id: string | null;
  current_date: string | null;
  proposed_date: string | null;
  current_hours: number;
  proposed_hours: number;
  current_allocation_type: string | null;
  proposed_allocation_type: string | null;
  current_outside_standard_hours: boolean;
  proposed_outside_standard_hours: boolean;
  locked: boolean;
};

export type DemandPlanDelta = {
  demand_number: string;
  available: boolean;
  reason: string | null;
  has_changes: boolean;
  add_count: number;
  modify_count: number;
  move_count: number;
  cancel_count: number;
  current_hours: number;
  proposed_hours: number;
  net_hours: number;
  items: DemandPlanDeltaItem[];
};

type ApiErrorPayload = {
  error?: { code?: string; message?: string };
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function getDemandPlanDelta(number: string): Promise<DemandPlanDelta> {
  const response = await fetch(
    `${API_BASE}/api/v1/demands/${encodeURIComponent(number)}/plan-delta`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      // Keep the stable fallback for non-JSON intermediaries.
    }
    throw new ApiError(
      payload?.error?.message || `Erreur HTTP ${response.status}`,
      response.status,
      payload?.error?.code ?? null,
    );
  }
  return response.json() as Promise<DemandPlanDelta>;
}
