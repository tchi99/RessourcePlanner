export type CommunicationContact = {
  recipient_id: string;
  audience: "technician" | "project_manager";
  display_name: string;
  email: string | null;
  active: boolean;
};

export type CommunicationDraft = {
  audience: "technician" | "project_manager";
  recipient_id: string;
  recipient_email: string;
  subject: string;
  body: string;
  message_kind: string;
  week_start: string;
  snapshot_fingerprint: string;
  requires_manual_approval: boolean;
};

export type CommunicationPreview = {
  week_start: string;
  mode: "weekly_plan" | "planning_change";
  snapshot_fingerprint: string;
  drafts: CommunicationDraft[];
  missing_contact_ids: string[];
  has_communicated_baseline: boolean;
  baseline_fingerprint: string | null;
};

export type CommunicationMessage = {
  id: string;
  audience: string;
  recipient_id: string;
  recipient_email: string;
  subject: string;
  body: string;
  included: boolean;
};

export type CommunicationBatch = {
  id: string;
  week_start: string;
  kind: string;
  snapshot_fingerprint: string;
  status: "PREPARED" | "APPROVED" | "CANCELLED" | "COMMUNICATED";
  prepared_by: string | null;
  prepared_at: string;
  approved_by: string | null;
  approved_at: string | null;
  communicated_by: string | null;
  communicated_at: string | null;
  cancelled_by: string | null;
  cancelled_at: string | null;
  drafts_provider: string | null;
  drafts_created_count: number;
  drafts_created_by: string | null;
  drafts_created_at: string | null;
  messages: CommunicationMessage[];
  stale: boolean;
};

export type CommunicationReview = {
  audience: string;
  recipient_id: string;
  include: boolean;
  subject: string;
  body: string;
};

type ApiErrorPayload = { error?: { message?: string } };
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      // Stable fallback for non-JSON server/proxy errors.
    }
    throw new Error(payload?.error?.message || `Erreur HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function listCommunicationContacts() {
  return request<CommunicationContact[]>("/api/v1/communications/contacts");
}

export function saveCommunicationContact(contact: CommunicationContact) {
  return request<CommunicationContact>(
    `/api/v1/communications/contacts/${encodeURIComponent(contact.recipient_id)}`,
    {
      method: "PUT",
      body: JSON.stringify({
        audience: contact.audience,
        display_name: contact.display_name,
        email: contact.email,
        active: contact.active,
      }),
    },
  );
}

export function getCommunicationPreview(weekStart: string) {
  return request<CommunicationPreview>(
    `/api/v1/communications/preview?week_start=${encodeURIComponent(weekStart)}`,
  );
}

export function prepareCommunicationBatch(
  weekStart: string,
  expectedFingerprint: string,
  reviews: CommunicationReview[],
) {
  return request<CommunicationBatch>("/api/v1/communications/batches", {
    method: "POST",
    body: JSON.stringify({
      week_start: weekStart,
      expected_fingerprint: expectedFingerprint,
      reviews,
    }),
  });
}

export function listCommunicationBatches(weekStart: string) {
  return request<CommunicationBatch[]>(
    `/api/v1/communications/batches?week_start=${encodeURIComponent(weekStart)}`,
  );
}

export function communicationBatchAction(
  batchId: string,
  action: "approve" | "create-drafts" | "cancel" | "mark-communicated",
) {
  return request<CommunicationBatch>(
    `/api/v1/communications/batches/${encodeURIComponent(batchId)}/${action}`,
    { method: "POST" },
  );
}
