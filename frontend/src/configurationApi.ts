import { csrfHeaders } from "./csrf";

export type SmtpConfiguration = {
  host: string | null;
  port: number;
  security: "STARTTLS" | "SSL_TLS";
  username: string | null;
  password_configured: boolean;
  from_email: string | null;
  from_name: string | null;
  reply_to: string | null;
  timeout_seconds: number;
  enabled: boolean;
  encryption_available: boolean;
  updated_by: string | null;
  updated_at: string | null;
};

export type SmtpTestLogEntry = {
  level: "INFO" | "SUCCESS" | "ERROR";
  step: string;
  message: string;
};

export type SmtpConnectionTestResult = {
  ok: boolean;
  message: string;
  log: SmtpTestLogEntry[];
};

export type SmtpConfigurationUpdate = {
  host: string;
  port: number;
  security: "STARTTLS" | "SSL_TLS";
  username: string | null;
  password: string | null;
  clear_password: boolean;
  from_email: string;
  from_name: string | null;
  reply_to: string | null;
  timeout_seconds: number;
  enabled: boolean;
};

type ErrorPayload = { error?: { code?: string; message?: string } };
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
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
    throw new Error(
      payload?.error?.message
      || `Erreur HTTP ${response.status}${payload?.error?.code ? ` (${payload.error.code})` : ""}`,
    );
  }
  return response.json() as Promise<T>;
}

export function getSmtpConfiguration(signal?: AbortSignal) {
  return request<SmtpConfiguration>("/api/v1/admin/settings/smtp", { signal });
}

export function saveSmtpConfiguration(payload: SmtpConfigurationUpdate) {
  return request<SmtpConfiguration>("/api/v1/admin/settings/smtp", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function testSmtpConnection() {
  return request<SmtpConnectionTestResult>("/api/v1/admin/settings/smtp/test", {
    method: "POST",
  });
}
