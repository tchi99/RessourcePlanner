import { ApiError } from "./api";
import { csrfHeaders } from "./csrf";

export type AssetTypeCatalogItem = {
  id: string;
  code: string;
  label: string;
  category: string;
  active: boolean;
  occupancy_policy: string;
  qualification_policy: string;
  required_competencies: { id: string; name: string }[];
  metadata: Record<string, unknown>;
};

export type AssetCatalogItem = {
  id: string;
  code: string;
  label: string;
  asset_type_id: string;
  active: boolean;
  metadata: Record<string, unknown>;
};

export type AssetCatalog = {
  types: AssetTypeCatalogItem[];
  assets: AssetCatalogItem[];
  planning_version: number;
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
    // Preserve the stable fallback for non-JSON proxy/server errors.
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
      ...csrfHeaders(),
      ...headers,
    },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

export function getAssetCatalog(signal?: AbortSignal) {
  return getJson<AssetCatalog>("/api/v1/assets/catalog", signal);
}

export type AssetOperatorCandidate = {
  resource_id: string;
  resource_name: string;
};

export type AssetOperatorCandidates = {
  requirement_id: string;
  allocation_id: string;
  qualification_state: "SATISFIED" | "MISSING_OPERATOR" | "SKILL_MISMATCH" | "NO_OVERLAP";
  required_competency_ids: string[];
  required_competency_names: string[];
  operator_resource_id: string | null;
  operator_resource_name: string | null;
  candidates: AssetOperatorCandidate[];
  planning_version: number;
};

export function getAssetOperatorCandidates(
  requirementId: string,
  signal?: AbortSignal,
) {
  return getJson<AssetOperatorCandidates>(
    `/api/v1/assets/requirements/${encodeURIComponent(requirementId)}/operator-candidates`,
    signal,
  );
}

export function setAssetRequirementOperator(
  requirementId: string,
  payload: {
    operator_resource_id: string | null;
    expected_planning_version: number;
  },
  idempotencyKey: string,
) {
  return sendJson<{
    planning_version: number;
    allocation_id: string;
    requirement_id: string;
    operator_resource_id: string | null;
    qualification_state: string;
  }>(
    `/api/v1/assets/requirements/${encodeURIComponent(requirementId)}/operator`,
    "PUT",
    payload,
    { "Idempotency-Key": idempotencyKey },
  );
}

export function reserveAssetRequirement(
  requirementId: string,
  payload: {
    asset_id: string | null;
    start_date?: string | null;
    end_date?: string | null;
    expected_planning_version: number;
  },
  idempotencyKey: string,
) {
  return sendJson<{ planning_version: number; allocation_id?: string | null; changed?: boolean }>(
    `/api/v1/assets/requirements/${encodeURIComponent(requirementId)}/reservation`,
    "PUT",
    payload,
    { "Idempotency-Key": idempotencyKey },
  );
}

export function addAssetUnavailability(
  assetId: string,
  payload: {
    start_date: string;
    end_date: string;
    reason: string | null;
    expected_planning_version: number;
  },
) {
  return sendJson<{ planning_version: number; id?: string }>(
    `/api/v1/assets/${encodeURIComponent(assetId)}/unavailability`,
    "POST",
    payload,
  );
}

export async function removeAssetUnavailability(
  assetId: string,
  unavailabilityId: string,
  expectedPlanningVersion: number,
) {
  const params = new URLSearchParams({
    expected_planning_version: String(expectedPlanningVersion),
  });
  const response = await fetch(
    `${API_BASE}/api/v1/assets/${encodeURIComponent(assetId)}/unavailability/${encodeURIComponent(unavailabilityId)}?${params.toString()}`,
    {
      method: "DELETE",
      headers: { Accept: "application/json", ...csrfHeaders() },
      credentials: "include",
    },
  );
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<{ planning_version: number; changed?: boolean }>;
}
