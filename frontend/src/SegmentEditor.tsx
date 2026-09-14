import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  DemandReadModel,
  ResourceReadModel,
  SegmentReadModel,
} from "./api";
import {
  SegmentWrite,
  assignSegment,
  cancelSegment,
  createSegment,
  getSegment,
  updateSegment,
} from "./segments-api";

type ConfirmationChoice = "inherit" | "Tentative" | "Confirmée";

type FormState = {
  start_date: string;
  end_date: string;
  planned_hours: string;
  status: string;
  description: string;
  required_competency: string;
  planning_type: string;
  priority: string;
  outside_standard_hours: boolean;
  confirmation: ConfirmationChoice;
  technician: string;
};

type RetryReceipt = { fingerprint: string; key: string };

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `web-segment-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function messageFromError(reason: unknown) {
  if (reason instanceof ApiError) {
    return `${reason.message}${reason.code ? ` (${reason.code})` : ""}`;
  }
  return reason instanceof Error ? reason.message : "Impossible d'enregistrer le segment.";
}

function confirmationChoice(segment: SegmentReadModel): ConfirmationChoice {
  if (!segment.confirmation_overridden) return "inherit";
  return segment.confirmation === "Tentative" ? "Tentative" : "Confirmée";
}

function formFromDemand(demand: DemandReadModel): FormState {
  const start = demand.desired_start ?? "";
  return {
    start_date: start,
    end_date: demand.desired_end ?? start,
    planned_hours: demand.estimated_hours == null ? "" : String(demand.estimated_hours),
    status: "À assigner",
    description: demand.description ?? "",
    required_competency: demand.required_competencies ?? "",
    planning_type: "Flexible",
    priority: demand.priority ?? "Normale",
    outside_standard_hours: false,
    confirmation: "inherit",
    technician: demand.proposed_resource ?? "",
  };
}

function formFromSegment(segment: SegmentReadModel): FormState {
  return {
    start_date: segment.start_date ?? "",
    end_date: segment.end_date ?? segment.start_date ?? "",
    planned_hours: String(segment.planned_hours || ""),
    status: segment.status || "À assigner",
    description: segment.description ?? "",
    required_competency: segment.required_competency ?? "",
    planning_type: segment.planning_type ?? "Flexible",
    priority: segment.priority ?? "Normale",
    outside_standard_hours: segment.outside_standard_hours,
    confirmation: confirmationChoice(segment),
    technician: segment.resource_name ?? "",
  };
}

export default function SegmentEditor({
  open,
  segmentId,
  demand,
  resources,
  onClose,
  onSaved,
}: {
  open: boolean;
  segmentId: string | null;
  demand: DemandReadModel | null;
  resources: ResourceReadModel[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [segment, setSegment] = useState<SegmentReadModel | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createRetry = useRef<RetryReceipt | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    createRetry.current = null;
    if (!segmentId) {
      setLoading(false);
      setSegment(null);
      setForm(demand ? formFromDemand(demand) : null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setSegment(null);
    setForm(null);
    getSegment(segmentId, controller.signal)
      .then((row) => {
        setSegment(row);
        setForm(formFromSegment(row));
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(messageFromError(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [open, segmentId, demand]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving && !cancelling) onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, saving, cancelling, onClose]);

  const sortedResources = useMemo(
    () => [...resources].sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name, "fr-CA")),
    [resources],
  );

  if (!open) return null;

  const effectiveDemandNumber = segment?.demand_number ?? demand?.number ?? null;
  const effectiveProjectNumber = segment?.project_number ?? demand?.project_number ?? null;
  const effectiveProjectName = segment?.project_name ?? demand?.project_name ?? null;
  const busy = loading || saving || cancelling;

  function setField<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((current) => current ? { ...current, [field]: value } : current);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form || busy) return;
    setError(null);

    const plannedHours = Number(form.planned_hours.replace(",", "."));
    if (!effectiveDemandNumber) {
      setError("Une demande est requise pour créer ou modifier un segment.");
      return;
    }
    if (!form.start_date || !form.end_date) {
      setError("Les dates de début et de fin sont requises.");
      return;
    }
    if (form.end_date < form.start_date) {
      setError("La date de fin ne peut pas précéder la date de début.");
      return;
    }
    if (!Number.isFinite(plannedHours) || plannedHours <= 0) {
      setError("Les heures prévues doivent être supérieures à zéro.");
      return;
    }

    const selectedTechnician = form.technician.trim();
    const technicianForUpdate = segmentId
      ? selectedTechnician
        ? segment?.resource_name ?? null
        : null
      : null;
    const payload: SegmentWrite = {
      demand_number: effectiveDemandNumber,
      project_number: effectiveProjectNumber,
      project_name: effectiveProjectName,
      technician: technicianForUpdate,
      start_date: form.start_date,
      end_date: form.end_date,
      planned_hours: plannedHours,
      status: form.status.trim() || "À assigner",
      description: form.description.trim(),
      source_effort_id: null,
      required_competency: form.required_competency.trim() || null,
      planning_type: form.planning_type.trim() || "Flexible",
      priority: form.priority.trim() || "Normale",
      outside_standard_hours: form.outside_standard_hours,
      confirmation: form.confirmation === "inherit" ? null : form.confirmation,
    };

    setSaving(true);
    try {
      let savedSegmentId = segmentId;
      if (segmentId) {
        await updateSegment(segmentId, payload);
      } else {
        const fingerprint = JSON.stringify(payload);
        const previous = createRetry.current;
        const key = previous?.fingerprint === fingerprint ? previous.key : newIdempotencyKey();
        createRetry.current = { fingerprint, key };
        const result = await createSegment(payload, key);
        savedSegmentId = result.segment_id;
        createRetry.current = null;
      }

      const technicianChanged = Boolean(selectedTechnician)
        && selectedTechnician !== (segment?.resource_name ?? "");
      if (savedSegmentId && technicianChanged) {
        await assignSegment(savedSegmentId, selectedTechnician);
      }
      onSaved();
    } catch (reason: unknown) {
      setError(messageFromError(reason));
    } finally {
      setSaving(false);
    }
  }

  async function cancelCurrentSegment() {
    if (!segmentId || busy) return;
    if (!window.confirm("Annuler ce segment? Le planning sera recalculé par le backend.")) return;
    setCancelling(true);
    setError(null);
    try {
      await cancelSegment(segmentId);
      onSaved();
    } catch (reason: unknown) {
      setError(messageFromError(reason));
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section className="segment-dialog" role="dialog" aria-modal="true" aria-labelledby="segment-dialog-title">
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">Besoin ressource</span>
            <h2 id="segment-dialog-title">{segmentId ? "Modifier le segment" : "Créer un segment"}</h2>
            <p>
              {effectiveDemandNumber ? `Demande ${effectiveDemandNumber}` : "Demande non définie"}
              {effectiveProjectNumber ? ` · ${effectiveProjectNumber}` : ""}
              {effectiveProjectName ? ` — ${effectiveProjectName}` : ""}
            </p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} disabled={busy} aria-label="Fermer">×</button>
        </div>

        {loading && !form ? <div className="segment-loading">Chargement du segment…</div> : form ? (
          <form className="segment-form" onSubmit={submit}>
            {error && <div className="dialog-error">{error}</div>}

            <div className="segment-context-grid">
              <div><span>Segment</span><strong>{segmentId || "Nouveau"}</strong></div>
              <div><span>Demande</span><strong>{effectiveDemandNumber || "—"}</strong></div>
              <div><span>Projet</span><strong>{effectiveProjectNumber || "—"}</strong></div>
              <div><span>Origine</span><strong>{segment?.origin || "Demande"}</strong></div>
            </div>

            <div className="segment-form-grid">
              <label>
                <span>Date de début</span>
                <input type="date" value={form.start_date} onChange={(event) => setField("start_date", event.target.value)} required />
              </label>
              <label>
                <span>Date de fin</span>
                <input type="date" value={form.end_date} onChange={(event) => setField("end_date", event.target.value)} required />
              </label>
              <label>
                <span>Heures prévues</span>
                <input type="number" min="0.25" step="0.25" value={form.planned_hours} onChange={(event) => setField("planned_hours", event.target.value)} required />
              </label>
              <label>
                <span>Statut</span>
                <input value={form.status} onChange={(event) => setField("status", event.target.value)} />
              </label>
              <label>
                <span>Type de planification</span>
                <select value={form.planning_type} onChange={(event) => setField("planning_type", event.target.value)}>
                  {!['Flexible', 'Fixe'].includes(form.planning_type) && <option value={form.planning_type}>{form.planning_type}</option>}
                  <option value="Flexible">Flexible</option>
                  <option value="Fixe">Fixe</option>
                </select>
              </label>
              <label>
                <span>Priorité</span>
                <select value={form.priority} onChange={(event) => setField("priority", event.target.value)}>
                  {!['Basse', 'Normale', 'Haute', 'Urgente'].includes(form.priority) && <option value={form.priority}>{form.priority}</option>}
                  <option value="Basse">Basse</option>
                  <option value="Normale">Normale</option>
                  <option value="Haute">Haute</option>
                  <option value="Urgente">Urgente</option>
                </select>
              </label>
              <label>
                <span>Compétence requise</span>
                <input value={form.required_competency} onChange={(event) => setField("required_competency", event.target.value)} />
              </label>
              <label>
                <span>Confirmation</span>
                <select value={form.confirmation} onChange={(event) => setField("confirmation", event.target.value as ConfirmationChoice)}>
                  <option value="inherit">Héritée de la demande</option>
                  <option value="Tentative">Tentative</option>
                  <option value="Confirmée">Confirmée</option>
                </select>
              </label>
              <label className="segment-assignment-field">
                <span>Ressource assignée</span>
                <select value={form.technician} onChange={(event) => setField("technician", event.target.value)}>
                  <option value="">Non assignée</option>
                  {segment?.resource_name && !resources.some((resource) => resource.name === segment.resource_name) && (
                    <option value={segment.resource_name}>{segment.resource_name} — inactive/inconnue</option>
                  )}
                  {sortedResources.map((resource) => (
                    <option value={resource.name} key={resource.id}>
                      {resource.name}{resource.resource_class ? ` — ${resource.resource_class}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label className="checkbox-field segment-outside-field">
                <input type="checkbox" checked={form.outside_standard_hours} onChange={(event) => setField("outside_standard_hours", event.target.checked)} />
                <span>Travail autorisé hors horaire standard</span>
              </label>
              <label className="segment-description-field">
                <span>Description</span>
                <textarea rows={4} value={form.description} onChange={(event) => setField("description", event.target.value)} />
              </label>
            </div>

            <div className="segment-help">
              <strong>Segment = besoin ressource; quart = affectation opérationnelle datée.</strong>
              <span>Les règles de validation et le recalcul du planning restent dans FastAPI. Une affectation choisie ici utilise la commande backend d'assignation du segment.</span>
            </div>

            <div className="dialog-actions segment-dialog-actions">
              {segmentId && segment?.status !== "Annulé" && (
                <button type="button" className="danger-button" onClick={cancelCurrentSegment} disabled={busy}>
                  {cancelling ? "Annulation…" : "Annuler le segment"}
                </button>
              )}
              <span className="dialog-action-spacer" />
              <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Fermer</button>
              <button type="submit" className="primary-button" disabled={busy}>
                {saving ? "Enregistrement…" : segmentId ? "Enregistrer" : "Créer le segment"}
              </button>
            </div>
          </form>
        ) : (
          <div className="dialog-error">{error || "Impossible d'initialiser l'éditeur de segment."}</div>
        )}
      </section>
    </div>
  );
}
