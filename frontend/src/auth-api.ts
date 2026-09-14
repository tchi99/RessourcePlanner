import { ApiError } from "./api";

export type AuthPrincipal = {
  local_user_id: string | null;
  issuer: string;
  subject: string;
  display_name: string;
  email: string | null;
  roles: string[];
  permissions: string[];
  auth_mode: string;
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function getCurrentPrincipal(signal?: AbortSignal): Promise<AuthPrincipal> {
  const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
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
    throw new ApiError(message, response.status, code);
  }
  return response.json() as Promise<AuthPrincipal>;
}
