import { csrfHeaders } from "./csrf";

export type AcumaticaIntegrationStatus = {
  configured: boolean;
  source?: string;
  feed?: string;
  page_size?: number;
  timeout_seconds?: number;
};

export type ProjectSyncResult = {
  received: number;
  created: number;
  updated: number;
  unchanged: number;
};

export type EmployeeSyncResult = {
  received: number;
  created: number;
  updated: number;
  unchanged: number;
  errors: number;
};

type ErrorPayload = { error?: { code?: string; message?: string } };
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...csrfHeaders(),
      ...(init?.headers ?? {}),
    },
    credentials: "include",
  });
  if (!response.ok) {
    let payload: ErrorPayload | null = null;
    try {
      payload = (await response.json()) as ErrorPayload;
    } catch {
      // Stable fallback below.
    }
    const detail = payload?.error?.code ? ` (${payload.error.code})` : "";
    throw new Error(payload?.error?.message
      ? `${payload.error.message}${detail}`
      : `Erreur HTTP ${response.status}${detail}`);
  }
  return response.json() as Promise<T>;
}

export function getAcumaticaIntegrationStatus(signal?: AbortSignal) {
  return request<AcumaticaIntegrationStatus>("/api/v1/integrations/acumatica", { signal });
}

export function syncAcumaticaProjects() {
  return request<ProjectSyncResult>("/api/v1/integrations/acumatica/projects/sync", {
    method: "POST",
  });
}

export function syncAcumaticaEmployees() {
  return request<EmployeeSyncResult>("/api/v1/integrations/acumatica/employees/sync", {
    method: "POST",
  });
}
