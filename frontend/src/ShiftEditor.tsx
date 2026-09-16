import { FormEvent, useEffect, useMemo, useState } from "react";

import { useAuth } from "./AuthContext";
import {
  ApiError,
  ResourceReadModel,
  ShiftReadModel,
  updateAllocation,
} from "./api";
import PlanningHistoryPanel from "./PlanningHistoryPanel";
import SegmentEditor from "./SegmentEditor";

type ConfirmationChoice = "inherit" | "Tentative" | "Confirmée";

function confirmationChoice(shift: ShiftReadModel): ConfirmationChoice {
  if (shift.confirmation_override === "Tentative") return "Tentative";
  if (shift.confirmation_override) return "Confirmée";
  return "inherit";
}

export default function ShiftEditor({
  shift,
  resources,
  onClose,
  onSaved,
}: {
  shift: ShiftReadModel;
  resources: ResourceReadModel[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { can } = useAuth();
  const canManagePlanning = can("manage_planning");
  const [technician, setTechnician] = useState(shift.resource_name);
  const [day, setDay] = useState(shift.work_date);
  const [hours, setHours] = useState(String(shift.hours));
  const [outsideStandardHours, setOutsideStandardHours] = useState(shift.outside_standard_hours);
  const [note, setNote] = useState(shift.note ?? "");
  const [confirmation, setConfirmation] = useState<ConfirmationChoice>(() => confirmationChoice(shift));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [segmentOpen, setSegmentOpen] = useState(false);

  useEffect(() => {
    if (!canManagePlanning || segmentOpen) return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, saving, segmentOpen, canManagePlanning]);

  const sortedResources = useMemo(
    () => [...resources].sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name, "fr-CA")),
    [resources],
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving || !canManagePlanning) return;
    const parsedHours = Number(hours);
    if (!technician.trim() || !day || !Number.isFinite(parsedHours) || parsedHours <= 0) {
      setError("Choisis un technicien, une date et un nombre d'heures supérieur à zéro.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await updateAllocation(shift.allocation_id, {
        technician,
        day,
        hours: parsedHours,
        outside_standard_hours: outsideStandardHours,
        note: note.trim(),
        confirmation: confirmation === "inherit" ? null : confirmation,
      });
      onSaved();
    } catch (reason) {
      if (reason instanceof ApiError) {
        setError(`${reason.message}${reason.code ? ` (${reason.code})` : ""}`);
      } else {
        setError(reason instanceof Error ? reason.message : "Impossible d'enregistrer le quart.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (!canManagePlanning) return null;

  if (segmentOpen) {
    return (
      <SegmentEditor
        open
        segmentId={shift.segment_id}
        demand={null}
        resources={resources}
        onClose={() => setSegmentOpen(false)}
        onSaved={onSaved}
      />
    );
  }

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <section className="shift-dialog" role="dialog" aria-modal="true" aria-labelledby="shift-dialog-title">
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">Quart {shift.allocation_id}</span>
            <h2 id="shift-dialog-title">Modifier le quart</h2>
            <p>
              {shift.project_number || "Projet"}
              {shift.project_name ? ` — ${shift.project_name}` : ""}
              {shift.demand_number ? ` · demande ${shift.demand_number}` : ""}
            </p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} disabled={saving} aria-label="Fermer">×</button>
        </div>

        <form className="shift-edit-form" onSubmit={submit}>
          {shift.source === "AUTO" && !shift.locked && (
            <div className="info-banner">
              Ce quart est généré automatiquement. L'enregistrer ici le transforme en décision manuelle verrouillée afin que le moteur ne l'écrase pas au prochain recalcul.
            </div>
          )}

          {error && <div className="dialog-error">{error}</div>}

          <div className="dialog-context-grid">
            <div><span>Segment</span><strong>{shift.segment_id}</strong></div>
            <div><span>Responsable projet</span><strong>{shift.project_manager || "—"}</strong></div>
            <div><span>Demandeur</span><strong>{shift.requester || "—"}</strong></div>
            <div><span>État</span><strong>{shift.locked ? "Verrouillé" : "Automatique"}</strong></div>
          </div>

          <div className="segment-parent-link">
            <div>
              <strong>Besoin ressource parent</strong>
              <span>Fenêtre, heures prévues, compétence, priorité, confirmation et règles hors horaire appartiennent au segment.</span>
            </div>
            <button type="button" className="secondary-button" onClick={() => setSegmentOpen(true)} disabled={saving}>
              Modifier le segment parent
            </button>
          </div>

          <div className="dialog-form-grid">
            <label><span>Technicien</span><select value={technician} onChange={(event) => setTechnician(event.target.value)} required>{sortedResources.map((resource) => <option value={resource.name} key={resource.id}>{resource.name}{resource.resource_class ? ` — ${resource.resource_class}` : ""}</option>)}</select></label>
            <label><span>Date</span><input type="date" value={day} onChange={(event) => setDay(event.target.value)} required /></label>
            <label><span>Heures</span><input type="number" min="0.25" step="0.25" value={hours} onChange={(event) => setHours(event.target.value)} required /></label>
            <label><span>Confirmation</span><select value={confirmation} onChange={(event) => setConfirmation(event.target.value as ConfirmationChoice)}><option value="inherit">Héritée du segment</option><option value="Tentative">Tentative</option><option value="Confirmée">Confirmée</option></select></label>
            <label className="checkbox-field"><input type="checkbox" checked={outsideStandardHours} onChange={(event) => setOutsideStandardHours(event.target.checked)} /><span>Autoriser / marquer hors horaire standard</span></label>
            <label className="span-2"><span>Note</span><textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} /></label>
          </div>

          <div className="confirmation-help">
            <strong>Confirmation effective : {shift.confirmation || "—"}</strong>
            <span>« Héritée » supprime l'override du quart. Tentative ou Confirmée crée un choix explicite au niveau du quart.</span>
          </div>

          <PlanningHistoryPanel entityType="SHIFT" reference={shift.allocation_id} />

          <div className="dialog-actions">
            <button type="button" className="secondary-button" onClick={onClose} disabled={saving}>Annuler</button>
            <button type="submit" className="primary-button" disabled={saving}>{saving ? "Enregistrement…" : "Enregistrer les modifications"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
