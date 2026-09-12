import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  ProjectReadModel,
  WorkPackageReadModel,
  WorkPackageWrite,
  createWorkPackage,
  updateWorkPackage,
} from "./api";

const STATUS_OPTIONS = [
  ["planned", "Planifié"],
  ["active", "Actif"],
  ["closed", "Fermé"],
  ["cancelled", "Annulé"],
] as const;

type FormState = {
  projectNumber: string;
  code: string;
  name: string;
  description: string;
  startDate: string;
  endDate: string;
  plannedHours: string;
  status: string;
};

function initialState(
  workPackage: WorkPackageReadModel | null,
  defaultProjectNumber: string,
): FormState {
  return {
    projectNumber: workPackage?.project_number || defaultProjectNumber,
    code: workPackage?.code || "",
    name: workPackage?.name || "",
    description: workPackage?.description || "",
    startDate: workPackage?.start_date || "",
    endDate: workPackage?.end_date || "",
    plannedHours: workPackage?.planned_hours == null ? "" : String(workPackage.planned_hours),
    status: workPackage?.status || "planned",
  };
}

function toPayload(form: FormState): WorkPackageWrite {
  const hours = form.plannedHours.trim();
  return {
    project_number: form.projectNumber,
    code: form.code.trim() || null,
    name: form.name.trim(),
    description: form.description.trim() || null,
    start_date: form.startDate || null,
    end_date: form.endDate || null,
    planned_hours: hours ? Number(hours.replace(",", ".")) : null,
    status: form.status,
  };
}

export default function WorkPackageEditor({
  projects,
  workPackage,
  defaultProjectNumber,
  onClose,
  onSaved,
}: {
  projects: ProjectReadModel[];
  workPackage: WorkPackageReadModel | null;
  defaultProjectNumber: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState(() => initialState(workPackage, defaultProjectNumber));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createRetry = useRef<{ fingerprint: string; key: string } | null>(null);
  const editing = Boolean(workPackage);

  useEffect(() => {
    setForm(initialState(workPackage, defaultProjectNumber));
    setError(null);
    createRetry.current = null;
  }, [workPackage, defaultProjectNumber]);

  const projectOptions = useMemo(
    () => [...projects].sort((left, right) => left.number.localeCompare(right.number, "fr-CA")),
    [projects],
  );

  function field<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    setError(null);

    const payload = toPayload(form);
    if (!payload.project_number) {
      setError("Choisis un projet.");
      return;
    }
    if (!payload.name) {
      setError("Le nom du WorkPackage est requis.");
      return;
    }
    if (payload.planned_hours != null && (!Number.isFinite(payload.planned_hours) || payload.planned_hours < 0)) {
      setError("Les heures prévues doivent être un nombre positif ou nul.");
      return;
    }
    if (payload.start_date && payload.end_date && payload.end_date < payload.start_date) {
      setError("La date de fin ne peut pas précéder la date de début.");
      return;
    }

    setSaving(true);
    try {
      if (workPackage) {
        await updateWorkPackage(workPackage.reference, payload);
      } else {
        const fingerprint = JSON.stringify(payload);
        const previous = createRetry.current;
        const key = previous?.fingerprint === fingerprint
          ? previous.key
          : crypto.randomUUID();
        createRetry.current = { fingerprint, key };
        await createWorkPackage(payload, key);
      }
      onSaved();
    } catch (reason: unknown) {
      if (reason instanceof ApiError) {
        setError(`${reason.message}${reason.code ? ` (${reason.code})` : ""}`);
      } else {
        setError(reason instanceof Error ? reason.message : "Impossible d’enregistrer le WorkPackage.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="wp-editor-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="wp-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="wp-editor-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="wp-editor-header">
          <div>
            <span className="eyebrow">WorkPackage</span>
            <h2 id="wp-editor-title">{editing ? "Modifier le lot" : "Créer un lot"}</h2>
            {workPackage && <small>Référence : {workPackage.reference}</small>}
          </div>
          <button type="button" className="wp-close" onClick={onClose} aria-label="Fermer">×</button>
        </header>

        <form className="wp-form" onSubmit={save}>
          <label className="wp-full">
            <span>Projet *</span>
            <select
              required
              value={form.projectNumber}
              onChange={(event) => field("projectNumber", event.target.value)}
            >
              <option value="">Choisir un projet</option>
              {projectOptions.map((project) => (
                <option value={project.number} key={project.id}>
                  {project.number} — {project.name}
                </option>
              ))}
            </select>
            {editing && (
              <small>
                Le projet peut être changé seulement si aucune demande n’est déjà liée à ce WorkPackage.
              </small>
            )}
          </label>

          <label>
            <span>Code</span>
            <input value={form.code} onChange={(event) => field("code", event.target.value)} placeholder="DEV, INST, MES…" />
          </label>
          <label>
            <span>Statut</span>
            <select value={form.status} onChange={(event) => field("status", event.target.value)}>
              {STATUS_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>

          <label className="wp-full">
            <span>Nom *</span>
            <input required value={form.name} onChange={(event) => field("name", event.target.value)} placeholder="Développement automatisation" />
          </label>

          <label>
            <span>Début</span>
            <input type="date" value={form.startDate} onChange={(event) => field("startDate", event.target.value)} />
          </label>
          <label>
            <span>Fin</span>
            <input type="date" value={form.endDate} onChange={(event) => field("endDate", event.target.value)} />
          </label>

          <label>
            <span>Heures prévues</span>
            <input
              type="number"
              min="0"
              step="0.5"
              value={form.plannedHours}
              onChange={(event) => field("plannedHours", event.target.value)}
              placeholder="80"
            />
          </label>

          <label className="wp-full">
            <span>Description</span>
            <textarea
              rows={4}
              value={form.description}
              onChange={(event) => field("description", event.target.value)}
              placeholder="Portée, livrables ou contexte du lot…"
            />
          </label>

          {error && <div className="wp-error wp-full">{error}</div>}

          <footer className="wp-editor-actions wp-full">
            <button type="button" className="wp-secondary" onClick={onClose} disabled={saving}>Annuler</button>
            <button type="submit" className="wp-primary" disabled={saving}>
              {saving ? "Enregistrement…" : editing ? "Enregistrer" : "Créer le WorkPackage"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
