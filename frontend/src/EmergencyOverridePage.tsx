import { useEffect, useMemo, useState } from "react";

import { ApiError, type DemandReadModel, getDemand, getDemands } from "./api";
import { emergencyPlanDemand } from "./demandWorkflowApi";

type EmergencyDemand = DemandReadModel & {
  emergency_override_active?: boolean;
  emergency_override_reason?: string | null;
  emergency_override_by?: string | null;
  emergency_override_at?: string | null;
};

function normalize(value: string | null | undefined) {
  return (value ?? "").trim().toLocaleLowerCase("fr-CA");
}

function errorMessage(reason: unknown): string {
  if (reason instanceof ApiError) {
    return `${reason.message}${reason.code ? ` (${reason.code})` : ""}`;
  }
  return reason instanceof Error ? reason.message : "Impossible de planifier la demande en urgence.";
}

function isEmergencyCandidate(demand: EmergencyDemand) {
  return normalize(demand.status) === "soumise" && normalize(demand.priority).startsWith("urgent");
}

export default function EmergencyOverridePage() {
  const [demands, setDemands] = useState<EmergencyDemand[]>([]);
  const [selectedNumber, setSelectedNumber] = useState("");
  const [selected, setSelected] = useState<EmergencyDemand | null>(null);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function refresh(number?: string) {
    const rows = (await getDemands()) as EmergencyDemand[];
    const candidates = rows.filter(
      (row) => isEmergencyCandidate(row) || Boolean(row.emergency_override_active),
    );
    setDemands(candidates);
    const wanted = number || selectedNumber || candidates[0]?.number || "";
    const next = candidates.some((row) => row.number === wanted)
      ? wanted
      : candidates[0]?.number || "";
    setSelectedNumber(next);
    if (!next) {
      setSelected(null);
      return;
    }
    setSelected((await getDemand(next)) as EmergencyDemand);
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    getDemands()
      .then(async (rows) => {
        if (!active) return;
        const candidates = (rows as EmergencyDemand[]).filter(
          (row) => isEmergencyCandidate(row) || Boolean(row.emergency_override_active),
        );
        setDemands(candidates);
        const first = candidates[0]?.number || "";
        setSelectedNumber(first);
        if (first) {
          const detail = (await getDemand(first)) as EmergencyDemand;
          if (active) setSelected(detail);
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selectedNumber || loading) return;
    let active = true;
    getDemand(selectedNumber)
      .then((row) => {
        if (active) setSelected(row as EmergencyDemand);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    return () => { active = false; };
  }, [selectedNumber, loading]);

  const canAttempt = useMemo(
    () => Boolean(selected && isEmergencyCandidate(selected) && !selected.emergency_override_active),
    [selected],
  );

  async function applyOverride() {
    if (!selected || submitting) return;
    const justification = reason.trim();
    if (!justification) {
      setError("Une justification est obligatoire pour une dérogation d’approbation.");
      return;
    }
    const confirmed = window.confirm(
      "PLANIFICATION EN URGENCE\n\nCette action crée le plan opérationnel sans approuver normalement la demande. Le coordonnateur doit être informé et la demande restera Soumise jusqu’à sa régularisation formelle. Continuer?",
    );
    if (!confirmed) return;

    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await emergencyPlanDemand(selected.number, justification);
      await refresh(result.demand_number);
      const planning = result.planning;
      setNotice(
        planning
          ? `Dérogation enregistrée. ${planning.segments} segment(s) et ${planning.allocations} quart(s) dans le plan; la demande demeure Soumise.`
          : "Dérogation enregistrée; la demande demeure Soumise jusqu’à l’approbation régulière.",
      );
      setReason("");
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="demand-workflow-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Exception contrôlée</span>
          <h1>Planification en urgence</h1>
          <p>Dérogation temporaire réservée aux demandes Urgentes et à la semaine courante. FastAPI valide l’admissibilité et conserve l’approbation régulière distincte.</p>
        </div>
      </div>

      {error && <div className="error-panel"><strong>Dérogation refusée.</strong><span>{error}</span></div>}
      {notice && <div className="demand-notice" role="status">{notice}</div>}

      <div className="workflow-layout">
        <aside className="workflow-list-panel">
          <label>
            <span>Demande urgente</span>
            <select
              value={selectedNumber}
              onChange={(event) => {
                setSelectedNumber(event.target.value);
                setReason("");
                setError(null);
                setNotice(null);
              }}
              disabled={loading || submitting}
            >
              {demands.map((demand) => (
                <option value={demand.number} key={demand.number}>
                  {demand.number} — {demand.project_number || "Sans projet"}{demand.emergency_override_active ? " — DÉROGATION ACTIVE" : ""}
                </option>
              ))}
            </select>
          </label>
        </aside>

        <div className="workflow-detail-panel">
          {selected ? (
            <>
              <div className="workflow-state-grid">
                <div className="workflow-state-card">
                  <span>Statut régulier</span>
                  <strong>{selected.status}</strong>
                  <small>La dérogation ne transforme jamais ce statut en approbation.</small>
                </div>
                <div className="workflow-state-card">
                  <span>Priorité</span>
                  <strong>{selected.priority || "Non définie"}</strong>
                  <small>Seules les demandes Urgentes sont admissibles.</small>
                </div>
              </div>

              {selected.emergency_override_active ? (
                <div className="workflow-separation-note" data-testid="emergency-override-active">
                  <strong>⚠ Dérogation d’approbation active</strong>
                  <span>
                    {selected.emergency_override_by ? `Par ${selected.emergency_override_by}. ` : ""}
                    {selected.emergency_override_reason || "Une régularisation par l’approbation normale est requise."}
                  </span>
                </div>
              ) : (
                <>
                  <div className="workflow-separation-note">
                    <strong>Le coordonnateur doit être informé.</strong>
                    <span>Cette action matérialise le plan sans approuver la demande. Une deuxième dérogation est interdite tant que l’approbation régulière n’a pas régularisé la demande.</span>
                  </div>
                  <label className="workflow-comment-field">
                    <span>Justification de l’urgence (requise)</span>
                    <textarea
                      rows={4}
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      disabled={submitting}
                      placeholder="Pourquoi le besoin doit-il être planifié avant l’approbation régulière?"
                    />
                  </label>
                  <div className="workflow-actions">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={!canAttempt || !reason.trim() || submitting}
                      onClick={applyOverride}
                    >
                      {submitting ? "Planification…" : "Planifier en urgence"}
                    </button>
                  </div>
                  <small className="workflow-authority-note">
                    L’interface ne calcule pas la semaine admissible : FastAPI refuse toute demande hors semaine courante, non Soumise, non Urgente ou déjà dérogée.
                  </small>
                </>
              )}
            </>
          ) : (
            <div className="demand-editor-empty">
              <strong>{loading ? "Chargement…" : "Aucune demande Urgente soumise ou dérogation active"}</strong>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
