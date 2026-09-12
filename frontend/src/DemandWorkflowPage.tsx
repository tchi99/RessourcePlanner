import { useEffect, useMemo, useState } from "react";

import { ApiError, type DemandReadModel, getDemand, getDemands } from "./api";
import {
  approveDemand,
  cancelDemand,
  requestDemandCorrection,
  submitDemand,
  type DemandWorkflowResult,
} from "./demandWorkflowApi";

type WorkflowAction = "submit" | "approve" | "correction" | "cancel";

function errorMessage(reason: unknown): string {
  if (reason instanceof ApiError) {
    return `${reason.message}${reason.code ? ` (${reason.code})` : ""}`;
  }
  return reason instanceof Error ? reason.message : "Impossible d'exécuter l'action.";
}

function normalStatus(status: string | null | undefined): string {
  return (status ?? "").trim().toLocaleLowerCase("fr-CA");
}

function expectedActions(status: string): WorkflowAction[] {
  const normalized = normalStatus(status);
  if (normalized === "brouillon" || normalized === "à corriger" || normalized === "a corriger") {
    return ["submit", "cancel"];
  }
  if (normalized === "soumise") return ["approve", "correction", "cancel"];
  if (normalized === "en planification") return ["cancel"];
  if (normalized === "annulée" || normalized === "annulee" || normalized === "fermé" || normalized === "ferme") {
    return [];
  }
  return ["submit", "approve", "correction", "cancel"];
}

function actionLabel(action: WorkflowAction): string {
  switch (action) {
    case "submit": return "Soumettre";
    case "approve": return "Approuver";
    case "correction": return "Demander une correction";
    case "cancel": return "Annuler la demande";
  }
}

export default function DemandWorkflowPage() {
  const [demands, setDemands] = useState<DemandReadModel[]>([]);
  const [selectedNumber, setSelectedNumber] = useState("");
  const [selectedDemand, setSelectedDemand] = useState<DemandReadModel | null>(null);
  const [approvalComment, setApprovalComment] = useState("");
  const [correctionComment, setCorrectionComment] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<WorkflowAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function refresh(number?: string) {
    const rows = await getDemands();
    setDemands(rows);
    const wanted = number || selectedNumber || rows[0]?.number || "";
    const nextNumber = rows.some((row) => row.number === wanted) ? wanted : rows[0]?.number || "";
    setSelectedNumber(nextNumber);
    if (!nextNumber) {
      setSelectedDemand(null);
      return;
    }
    const detail = await getDemand(nextNumber);
    setSelectedDemand(detail);
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    getDemands()
      .then(async (rows) => {
        if (!active) return;
        setDemands(rows);
        const first = rows[0]?.number || "";
        setSelectedNumber(first);
        if (first) {
          const detail = await getDemand(first);
          if (active) setSelectedDemand(detail);
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
    setError(null);
    getDemand(selectedNumber)
      .then((detail) => {
        if (active) setSelectedDemand(detail);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    return () => { active = false; };
  }, [selectedNumber, loading]);

  const actions = useMemo(
    () => expectedActions(selectedDemand?.status ?? ""),
    [selectedDemand?.status],
  );

  async function runAction(action: WorkflowAction) {
    if (!selectedDemand || pendingAction) return;
    if (action === "correction" && !correctionComment.trim()) {
      setError("Un commentaire est requis pour demander une correction.");
      return;
    }
    if (action === "cancel" && !window.confirm(`Annuler la demande ${selectedDemand.number}?`)) return;

    setPendingAction(action);
    setError(null);
    setNotice(null);
    try {
      let result: DemandWorkflowResult;
      if (action === "submit") {
        result = await submitDemand(selectedDemand.number);
      } else if (action === "approve") {
        result = await approveDemand(selectedDemand.number, approvalComment.trim());
      } else if (action === "correction") {
        result = await requestDemandCorrection(selectedDemand.number, correctionComment.trim());
      } else {
        result = await cancelDemand(selectedDemand.number);
      }

      await refresh(result.demand_number);
      if (action === "approve") {
        const planning = result.planning;
        setNotice(
          planning
            ? `Demande approuvée. Planification recalculée : ${planning.segments} segment(s), ${planning.allocations} allocation(s), ${planning.unallocated_hours} h non allouée(s).`
            : "Demande approuvée.",
        );
        setApprovalComment("");
      } else if (action === "correction") {
        setNotice("Demande retournée pour correction.");
        setCorrectionComment("");
      } else if (action === "submit") {
        setNotice("Demande soumise pour approbation.");
      } else {
        setNotice("Demande annulée.");
      }
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setPendingAction(null);
    }
  }

  const busy = pendingAction !== null;

  return (
    <section className="demand-workflow-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Cycle de vie</span>
          <h1>Workflow des demandes</h1>
          <p>Soumission, approbation, retour pour correction et annulation via les règles autoritaires de FastAPI.</p>
        </div>
      </div>

      {error && <div className="error-panel"><strong>Action impossible.</strong><span>{error}</span></div>}
      {notice && <div className="demand-notice" role="status">{notice}</div>}

      <div className="workflow-layout">
        <aside className="workflow-list-panel">
          <label>
            <span>Demande</span>
            <select
              value={selectedNumber}
              onChange={(event) => {
                setSelectedNumber(event.target.value);
                setNotice(null);
                setError(null);
                setApprovalComment("");
                setCorrectionComment("");
              }}
              disabled={busy || loading}
            >
              {demands.map((demand) => (
                <option value={demand.number} key={demand.number}>
                  {demand.number} — {demand.project_number || "Sans projet"} — {demand.status}
                </option>
              ))}
            </select>
          </label>
          {selectedDemand && (
            <div className="workflow-summary-card">
              <strong>{selectedDemand.number}</strong>
              <span>{selectedDemand.project_number} — {selectedDemand.project_name || "Projet"}</span>
              <span>{selectedDemand.requester ? `Demandeur : ${selectedDemand.requester}` : "Demandeur non défini"}</span>
            </div>
          )}
        </aside>

        <div className="workflow-detail-panel">
          {selectedDemand ? (
            <>
              <div className="workflow-state-grid">
                <div className="workflow-state-card">
                  <span>Approbation / statut</span>
                  <strong>{selectedDemand.status || "Non défini"}</strong>
                  <small>Ce statut pilote le cycle de vie de la demande.</small>
                </div>
                <div className="workflow-state-card">
                  <span>Confirmation</span>
                  <strong>{selectedDemand.confirmation || "Confirmée"}</strong>
                  <small>La confirmation décrit la certitude du besoin, indépendamment de son approbation.</small>
                </div>
              </div>

              <div className="workflow-separation-note">
                <strong>Approbation ≠ confirmation.</strong>
                <span>Une demande peut être approuvée tout en restant Tentative; les deux concepts ne sont jamais fusionnés par l’interface.</span>
              </div>

              {actions.includes("approve") && (
                <label className="workflow-comment-field">
                  <span>Commentaire d’approbation (optionnel)</span>
                  <textarea
                    rows={3}
                    value={approvalComment}
                    onChange={(event) => setApprovalComment(event.target.value)}
                    disabled={busy}
                    placeholder="Contexte ou décision d’approbation…"
                  />
                </label>
              )}

              {actions.includes("correction") && (
                <label className="workflow-comment-field">
                  <span>Commentaire de correction (requis)</span>
                  <textarea
                    rows={3}
                    value={correctionComment}
                    onChange={(event) => setCorrectionComment(event.target.value)}
                    disabled={busy}
                    placeholder="Indiquer précisément ce qui doit être corrigé…"
                  />
                </label>
              )}

              <div className="workflow-actions">
                {actions.length === 0 && <span className="workflow-terminal-state">Aucune transition usuelle disponible pour ce statut.</span>}
                {actions.includes("submit") && (
                  <button type="button" className="primary-button" disabled={busy} onClick={() => runAction("submit")}>
                    {pendingAction === "submit" ? "Soumission…" : actionLabel("submit")}
                  </button>
                )}
                {actions.includes("approve") && (
                  <button type="button" className="primary-button" disabled={busy} onClick={() => runAction("approve")}>
                    {pendingAction === "approve" ? "Approbation…" : actionLabel("approve")}
                  </button>
                )}
                {actions.includes("correction") && (
                  <button type="button" className="secondary-button" disabled={busy || !correctionComment.trim()} onClick={() => runAction("correction")}>
                    {pendingAction === "correction" ? "Envoi…" : actionLabel("correction")}
                  </button>
                )}
                {actions.includes("cancel") && (
                  <button type="button" className="secondary-button workflow-cancel" disabled={busy} onClick={() => runAction("cancel")}>
                    {pendingAction === "cancel" ? "Annulation…" : actionLabel("cancel")}
                  </button>
                )}
              </div>

              <small className="workflow-authority-note">
                L’interface suggère les transitions usuelles selon le statut affiché; FastAPI demeure l’autorité pour accepter ou refuser chaque commande.
              </small>
            </>
          ) : (
            <div className="demand-editor-empty">
              <strong>{loading ? "Chargement des demandes…" : "Aucune demande disponible"}</strong>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
