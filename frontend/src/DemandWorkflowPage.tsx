import { useEffect, useMemo, useState } from "react";

import { ApiError, type DemandReadModel, getDemand, getDemands } from "./api";
import {
  approveDemand,
  cancelDemand,
  getDemandWorkflowState,
  requestDemandCorrection,
  submitDemand,
  type DemandWorkflowResult,
  type DemandWorkflowState,
  type WorkflowAction,
} from "./demandWorkflowApi";
import {
  getDemandPlanDelta,
  type DemandPlanDelta,
  type DemandPlanDeltaItem,
} from "./planDeltaApi";
import "./planDelta.css";

type WorkflowButtonAction = Extract<
  WorkflowAction,
  "submit" | "approve" | "correction" | "cancel"
>;

function errorMessage(reason: unknown): string {
  if (reason instanceof ApiError) {
    return `${reason.message}${reason.code ? ` (${reason.code})` : ""}`;
  }
  return reason instanceof Error ? reason.message : "Impossible d'exécuter l'action.";
}

function normalStatus(status: string | null | undefined): string {
  return (status ?? "").trim().toLocaleLowerCase("fr-CA");
}

function actionLabel(action: WorkflowButtonAction): string {
  switch (action) {
    case "submit": return "Soumettre";
    case "approve": return "Approuver";
    case "correction": return "Demander une correction";
    case "cancel": return "Annuler la demande";
  }
}

function deltaLabel(change: DemandPlanDeltaItem["change"]): string {
  switch (change) {
    case "ADD": return "À ajouter";
    case "MOVE": return "À déplacer";
    case "MODIFY": return "À modifier";
    case "CANCEL": return "À annuler";
  }
}

function deltaSide(
  resource: string | null,
  day: string | null,
  hours: number,
  allocationType: string | null,
  outside: boolean,
): string {
  if (!day || !resource || hours <= 0) return "—";
  const suffix = outside ? " · hors horaire" : "";
  return `${day} · ${resource} · ${hours} h${allocationType ? ` · ${allocationType}` : ""}${suffix}`;
}

function unavailableDeltaMessage(reason: string | null): string {
  switch (reason) {
    case "NO_CURRENT_PLAN":
      return "Aucun plan approuvé antérieur : cette approbation créera le premier plan de la demande.";
    case "PROPOSAL_INCOMPLETE":
      return "Le plan proposé est incomplet; le delta ne peut pas encore être calculé.";
    case "CURRENT_PLAN_UNSUPPORTED":
    case "PROPOSED_PLAN_UNSUPPORTED":
      return "Le moteur ne peut pas comparer cette demande tant qu’un segment non supporté est présent.";
    default:
      return "Le delta n’est pas disponible pour cette demande.";
  }
}

export default function DemandWorkflowPage() {
  const [demands, setDemands] = useState<DemandReadModel[]>([]);
  const [selectedNumber, setSelectedNumber] = useState("");
  const [selectedDemand, setSelectedDemand] = useState<DemandReadModel | null>(null);
  const [workflowState, setWorkflowState] = useState<DemandWorkflowState | null>(null);
  const [approvalComment, setApprovalComment] = useState("");
  const [correctionComment, setCorrectionComment] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<WorkflowButtonAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [planDelta, setPlanDelta] = useState<DemandPlanDelta | null>(null);
  const [planDeltaLoading, setPlanDeltaLoading] = useState(false);
  const [planDeltaError, setPlanDeltaError] = useState<string | null>(null);

  async function refresh(number?: string) {
    const rows = await getDemands();
    setDemands(rows);
    const wanted = number || selectedNumber || rows[0]?.number || "";
    const nextNumber = rows.some((row) => row.number === wanted) ? wanted : rows[0]?.number || "";
    setSelectedNumber(nextNumber);
    if (!nextNumber) {
      setSelectedDemand(null);
      setWorkflowState(null);
      return;
    }
    const [detail, workflow] = await Promise.all([
      getDemand(nextNumber),
      getDemandWorkflowState(nextNumber),
    ]);
    setSelectedDemand(detail);
    setWorkflowState(workflow);
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
          const [detail, workflow] = await Promise.all([
            getDemand(first),
            getDemandWorkflowState(first),
          ]);
          if (active) {
            setSelectedDemand(detail);
            setWorkflowState(workflow);
          }
        } else if (active) {
          setWorkflowState(null);
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
    Promise.all([
      getDemand(selectedNumber),
      getDemandWorkflowState(selectedNumber),
    ])
      .then(([detail, workflow]) => {
        if (active) {
          setSelectedDemand(detail);
          setWorkflowState(workflow);
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    return () => { active = false; };
  }, [selectedNumber, loading]);

  useEffect(() => {
    if (!selectedDemand || normalStatus(selectedDemand.status) !== "soumise") {
      setPlanDelta(null);
      setPlanDeltaError(null);
      setPlanDeltaLoading(false);
      return;
    }
    let active = true;
    setPlanDeltaLoading(true);
    setPlanDeltaError(null);
    getDemandPlanDelta(selectedDemand.number)
      .then((delta) => {
        if (active) setPlanDelta(delta);
      })
      .catch((reason: unknown) => {
        if (active) {
          setPlanDelta(null);
          setPlanDeltaError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (active) setPlanDeltaLoading(false);
      });
    return () => { active = false; };
  }, [selectedDemand?.number, selectedDemand?.status]);

  const actions = useMemo(
    () =>
      (workflowState?.available_actions ?? []).filter(
        (action): action is WorkflowButtonAction =>
          action === "submit" ||
          action === "approve" ||
          action === "correction" ||
          action === "cancel",
      ),
    [workflowState],
  );

  async function runAction(action: WorkflowButtonAction) {
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
      const expectedVersion = workflowState?.version ?? selectedDemand.version;
      let result: DemandWorkflowResult;
      if (action === "submit") {
        result = await submitDemand(selectedDemand.number, expectedVersion);
      } else if (action === "approve") {
        result = await approveDemand(
          selectedDemand.number,
          approvalComment.trim(),
          expectedVersion,
        );
      } else if (action === "correction") {
        result = await requestDemandCorrection(
          selectedDemand.number,
          correctionComment.trim(),
          expectedVersion,
        );
      } else {
        result = await cancelDemand(selectedDemand.number, expectedVersion);
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

              {normalStatus(selectedDemand.status) === "soumise" && (
                <div className="plan-delta-panel" data-testid="plan-delta-preview">
                  <div className="plan-delta-heading">
                    <div>
                      <span className="eyebrow">Impact de l’approbation</span>
                      <h3>Plan actuel → plan proposé</h3>
                      <p>Prévisualisation en lecture seule calculée avec le moteur de planification. Aucun quart n’est modifié avant l’approbation.</p>
                    </div>
                    {planDelta?.available && (
                      <strong>{planDelta.net_hours >= 0 ? "+" : ""}{planDelta.net_hours} h touchées nettes</strong>
                    )}
                  </div>

                  {planDeltaLoading && <div className="plan-delta-empty">Calcul du delta…</div>}
                  {planDeltaError && <div className="plan-delta-unavailable">{planDeltaError}</div>}

                  {!planDeltaLoading && planDelta && !planDelta.available && (
                    <div className="plan-delta-unavailable">{unavailableDeltaMessage(planDelta.reason)}</div>
                  )}

                  {!planDeltaLoading && planDelta?.available && (
                    <>
                      <div className="plan-delta-summary">
                        <span className="plan-delta-badge">{planDelta.add_count} ajout(s)</span>
                        <span className="plan-delta-badge">{planDelta.move_count} déplacement(s)</span>
                        <span className="plan-delta-badge">{planDelta.modify_count} modification(s)</span>
                        <span className="plan-delta-badge">{planDelta.cancel_count} annulation(s)</span>
                      </div>

                      {!planDelta.has_changes ? (
                        <div className="plan-delta-empty">L’approbation ne changerait aucun quart du plan actuel.</div>
                      ) : (
                        <div className="plan-delta-list">
                          {planDelta.items.map((item, index) => (
                            <div className="plan-delta-row" key={`${item.segment_id}-${item.change}-${index}`}>
                              <strong>{deltaLabel(item.change)}</strong>
                              <div className="plan-delta-side">
                                <small>Actuel</small>
                                <span>{deltaSide(
                                  item.current_resource_name,
                                  item.current_date,
                                  item.current_hours,
                                  item.current_allocation_type,
                                  item.current_outside_standard_hours,
                                )}</span>
                              </div>
                              <div className="plan-delta-side">
                                <small>Proposé</small>
                                <span>{deltaSide(
                                  item.proposed_resource_name,
                                  item.proposed_date,
                                  item.proposed_hours,
                                  item.proposed_allocation_type,
                                  item.proposed_outside_standard_hours,
                                )}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

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
