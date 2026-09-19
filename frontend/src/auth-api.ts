import { csrfHeaders } from "./csrf";
import { ApiError } from "./api";

export type AuthPrincipal = {
  local_user_id: string | null;
  issuer: string;
  subject: string;
  display_name: string;
  email: string | null;
  employee_external_id: string | null;
  roles: string[];
  permissions: string[];
  auth_mode: string;
};

export type DevUserIdentity = {
  user_id: string;
  display_name: string;
  roles: string[];
  employee_external_id: string | null;
};

export type DevUserSwitcherState = {
  enabled: boolean;
  bootstrap: AuthPrincipal;
  users: DevUserIdentity[];
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function apiError(response: Response): Promise<ApiError> {
  let message = `Erreur HTTP ${response.status}`;
  let code: string | null = null;
  try {
    const payload = await response.json() as {
      error?: { message?: string; code?: string };
    };
    message = payload.error?.message || message;
    code = payload.error?.code ?? null;
  } catch {
    // Keep stable fallback for non-JSON proxy responses.
  }
  return new ApiError(message, response.status, code);
}

export function getLoginUrl(): string {
  return `${API_BASE}/api/v1/auth/login`;
}

export async function getCurrentPrincipal(signal?: AbortSignal): Promise<AuthPrincipal> {
  const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Accept: "application/json", ...csrfHeaders() },
    credentials: "include",
    signal,
  });
  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<AuthPrincipal>;
}

export async function logoutCurrentSession(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/auth/logout`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) throw await apiError(response);
}

export async function getDevUserSwitcher(signal?: AbortSignal): Promise<DevUserSwitcherState | null> {
  const response = await fetch(`${API_BASE}/api/v1/dev/user-switcher`, {
    headers: { Accept: "application/json" },
    credentials: "include",
    signal,
  });
  if (response.status === 404) return null;
  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<DevUserSwitcherState>;
}

export async function selectDevUser(userId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/dev/user-switcher/select`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", ...csrfHeaders() },
    credentials: "include",
    body: JSON.stringify({ user_id: userId }),
  });
  if (!response.ok) throw await apiError(response);
}

export async function resetDevUser(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/dev/user-switcher/reset`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) throw await apiError(response);
}
