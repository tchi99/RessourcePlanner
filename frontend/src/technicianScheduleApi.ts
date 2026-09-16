import { ApiError, ResourceReadModel, ShiftReadModel } from "./api";

export type TechnicianScheduleLinkStatus = "UNLINKED" | "RESOURCE_NOT_FOUND" | "LINKED";

export type TechnicianScheduleReadModel = {
  start: string;
  end: string;
  link_status: TechnicianScheduleLinkStatus;
  employee_external_id: string | null;
  resource: ResourceReadModel | null;
  shifts: ShiftReadModel[];
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function responseError(response: Response): Promise<ApiError> {
  let message = `Erreur HTTP ${response.status}`;
  let code: string | null = null;
  try {
    const payload = await response.json() as { error?: { message?: string; code?: string } };
    message = payload.error?.message || message;
    code = payload.error?.code ?? null;
  } catch {
    // Stable fallback for non-JSON proxy responses.
  }
  return new ApiError(message, response.status, code);
}

export async function getMySchedule(
  start: string,
  end: string,
  signal?: AbortSignal,
): Promise<TechnicianScheduleReadModel> {
  const params = new URLSearchParams({ start, end });
  const response = await fetch(`${API_BASE}/api/v1/me/schedule?${params.toString()}`, {
    headers: { Accept: "application/json" },
    credentials: "include",
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<TechnicianScheduleReadModel>;
}
