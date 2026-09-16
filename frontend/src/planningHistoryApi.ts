export type PlanningHistoryReadModel = {
  entity_type: string;
  entity_reference: string;
  parent_reference: string | null;
  action: string;
  occurred_at: string;
  details: string | null;
  actor_name: string | null;
};

type ApiErrorPayload = { error?: { message?: string } };
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function fetchHistory(path: string, signal?: AbortSignal) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    throw new Error(payload?.error?.message || `Erreur HTTP ${response.status}`);
  }
  return response.json() as Promise<PlanningHistoryReadModel[]>;
}

export function getSegmentHistory(segmentId: string, signal?: AbortSignal) {
  return fetchHistory(`/api/v1/segments/${encodeURIComponent(segmentId)}/history`, signal);
}

export function getShiftHistory(allocationId: string, signal?: AbortSignal) {
  return fetchHistory(`/api/v1/shifts/${encodeURIComponent(allocationId)}/history`, signal);
}
