import { useEffect, useState } from "react";

import {
  PlanningHistoryReadModel,
  getSegmentHistory,
  getShiftHistory,
} from "./planningHistoryApi";

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("fr-CA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function detailLines(details: string | null) {
  if (!details) return [];
  try {
    const parsed = JSON.parse(details) as {
      changes?: Record<string, { before?: unknown; after?: unknown }>;
      before?: Record<string, unknown>;
      after?: Record<string, unknown>;
    };
    if (parsed.changes) {
      return Object.entries(parsed.changes).map(
        ([field, value]) => `${field}: ${String(value.before ?? "—")} → ${String(value.after ?? "—")}`,
      );
    }
    const snapshot = parsed.after ?? parsed.before;
    if (snapshot) {
      return Object.entries(snapshot)
        .filter(([, value]) => value !== null && value !== "")
        .map(([field, value]) => `${field}: ${String(value)}`);
    }
  } catch {
    return [details];
  }
  return [];
}

export default function PlanningHistoryPanel({
  entityType,
  reference,
  refreshKey = 0,
}: {
  entityType: "SEGMENT" | "SHIFT";
  reference: string;
  refreshKey?: number;
}) {
  const [events, setEvents] = useState<PlanningHistoryReadModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const request = entityType === "SEGMENT"
      ? getSegmentHistory(reference, controller.signal)
      : getShiftHistory(reference, controller.signal);
    request
      .then(setEvents)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Impossible de charger l’historique.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [entityType, reference, refreshKey]);

  return (
    <section className="planning-history-panel" aria-label="Historique des changements">
      <div className="planning-history-heading">
        <div>
          <span className="eyebrow">Audit</span>
          <h3>Historique des changements</h3>
        </div>
        <span className="planning-history-reference">{reference}</span>
      </div>

      {error ? (
        <div className="dialog-error">{error}</div>
      ) : loading ? (
        <div className="planning-history-empty">Chargement de l’historique…</div>
      ) : events.length === 0 ? (
        <div className="planning-history-empty">Aucun événement métier enregistré.</div>
      ) : (
        <ol className="planning-history-timeline">
          {events.map((event, index) => {
            const lines = detailLines(event.details);
            return (
              <li key={`${event.occurred_at}-${event.action}-${index}`}>
                <div className="planning-history-event-heading">
                  <strong>{event.action}</strong>
                  <time>{formatDateTime(event.occurred_at)}</time>
                </div>
                <span className="planning-history-actor">{event.actor_name || "Acteur non enregistré"}</span>
                {event.parent_reference && <span className="planning-history-parent">Segment {event.parent_reference}</span>}
                {lines.length > 0 && (
                  <ul className="planning-history-changes">
                    {lines.map((line) => <li key={line}>{line}</li>)}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
