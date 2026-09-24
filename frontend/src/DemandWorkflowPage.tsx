import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type DemandDetailReadModel,
  type DemandReadModel,
  getDemandDetail,
  getDemands,
} from "./api";
import {
  approveDemand,
  cancelDemand,
  requestDemandCorrection,
  submitDemand,
  type DemandWorkflowResult,
  type DemandWorkflowState,
  type WorkflowAction,
} from "./demandWorkflowApi";
import {
  getDemandApprovalState,
  getDemandPlanDelta,
  type DemandApprovalState,
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

function envelopeDecisionLabel(decision: string | null): string {
  switch (decision) {
    case "WITHIN_ENVELOPE": return "Dans l’enveloppe approuvée";
    case "REAPPROVAL_REQUIRED": return "Réapprobation requise";
    case "EXPLICIT_EXCEPTION_REQUIRED": return "Dérogation explicite requise";
    case "APPROVAL_REFERENCE_UNKNOWN": return "Référence d’approbation inconnue";
    case "INVALID": return "Proposition invalide";
    default: return "Décision d’enveloppe non disponible";
  }
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

type DemandWorkflowPageProps = {
  demandNumber?: string;
  canonicalDetail?: DemandDetailReadModel | null;
  embedded?: boolean;
  onChanged?: () => void | Promise<void>;
  refreshToken?: number;
  hasUnsavedChanges?: boolean;
};

export default function DemandWorkflowPage({
  demandNumber,
  canonicalDetail,
  embedded = false,
  onChanged,
  refreshToken = 0,
  hasUnsavedChanges = false,
}: DemandWorkflowPageProps = {}) {
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
  const [approvalState, setApprovalState] = useState<DemandApprovalState | null>(null);
  const [approvalStateError, setApprovalStateError] = useState<string | null>(null);
  const [planDelta, setPlanDelta] = useState<DemandPlanDelta | null>(null);
  const [planDeltaLoading, setPlanDeltaLoading] = useState(false);
  const [planDeltaError, setPlanDeltaError] = useState<string | null>(null);

  async function refresh(number?: string) {
    const rows = demandNumber
      ? [(await getDemandDetail(demandNumber)).demand]
      : await getDemands();
    setDemands(rows);
    const wanted = demandNumber || number || selectedNumber || rows[0]?.number || "";
    const nextNumber = rows.some((row) => row.number === wanted) ? wanted : rows[0]?.number || "";
    setSelectedNumber(nextNumber);
    if (!nextNumber) {
      setSelectedDemand(null);
      setWorkflowState(null);
      return;
    }
    const detail = await getDemandDetail(nextNumber);
    setSelectedDemand(detail.demand);
    setWorkflowState(detail.workflow as DemandWorkflowState);
  }

  useEffect(() => {
    if (canonicalDetail) {
      setDemands([canonicalDetail.demand]);
      setSelectedNumber(canonicalDetail.demand.number);
      setSelectedDemand(canonicalDetail.demand);
      setWorkflowState(canonicalDetail.workflow as DemandWorkflowState);
      setLoading(false);
      setError(null);
      return;
    }
    let active = true;
    setLoading(true);
    setWorkflowState(null);
    const demandRequest = demandNumber
      ? getDemandDetail(demandNumber).then((detail) => [detail.demand])
      : getDemands();
    demandRequest
      .then(async (rows) => {
        if (!active) return;
        setDemands(rows);
        const first = demandNumber || rows[0]?.number || "";
        setSelectedNumber(first);
        if (first) {
          const detail = await getDemandDetail(first);
          if (active) {
            setSelectedDemand(detail.demand);
            setWorkflowState(detail.workflow as DemandWorkflowState);
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
  }, [demandNumber, refreshToken, canonicalDetail]);

  useEffect(() => {
    if (canonicalDetail || !selectedNumber || loading) return;
    let active = true;
    setError(null);
    getDemandDetail(selectedNumber)
      .then((detail) => {
        if (active) {
          setSelectedDemand(detail.demand);
          setWorkflowState(detail.workflow as DemandWorkflowState);
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    return () => { active = false; };
  }, [selectedNumber, loading]);

  useEffect(() => {
    if (!selectedDemand) {
      setApprovalState(null);
      setApprovalStateError(null);
      return;
    }
    let active = true;
    setApprovalStateError(null);
    getDemandApprovalState(selectedDemand.number)
      .then((state) => {
        if (active) setApprovalState(state);
      })
      .catch((reason: unknown) => {
        if (active) {
          setApprovalState(null);
          setApprovalStateError(errorMessage(reason));
        }
      });
    return () => { active = false; };
  }, [selectedDemand?.number, selectedDemand?.version, selectedDemand?.status]);

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
    if (hasUnsavedChanges) {
      setError("Enregistre les modifications avant de poursuivre.");
      return;
    }
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

      if (canonicalDetail) {
        await onChanged?.();
      } else {
        await refresh(result.demand_number);
        await onChanged?.();
      }
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
      {!embedded && (
        <div className="page-heading">
          <div>
            <span className="eyebrow">Cycle de vie</span>
            <h1>Workflow des demandes</h1>
            <p>Soumission, approbation, retour pour correction et annulation via les règles autoritaires de FastAPI.</p>
          </div>
        </div>
      )}

      {error && <div className="error-panel"><strong>Action impossible.</strong><span>{error}</span></div>}
      {notice && <div className="demand-notice" role="status">{notice}</div>}
      {hasUnsavedChanges && (
        <div className="demand-notice workflow-dirty-warning" role="status">
          Enregistre les modifications avant de poursuivre.
        </div>
      )}

      <div className={`workflow-layout ${embedded ? "embedded" : ""}`}>
        {!embedded && (        <aside className="workflow-list-panel">
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
        </aside>)}

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
                {approvalState && (
                  <div className="workflow-state-card" data-testid="approval-state">
                    <span>Autorisation active</span>
                    <strong>{approvalState.approval_reference_status || "Aucune référence"}</strong>
                    <small>
                      {approvalState.active_revision_id
                        ? `Révision ${approvalState.active_revision_id.slice(0, 8)} · demande approuvée v${approvalState.approved_request_version ?? "—"} · opérationnel v${approvalState.operational_version ?? "—"}`
                        : "Aucune révision approuvée active."}
                    </small>
                    {approvalState.authorization_fingerprint && (
                      <small title={approvalState.authorization_fingerprint}>
                        Empreinte {approvalState.authorization_fingerprint.slice(0, 12)}…
                      </small>
                    )}
                  </div>
                )}
              </div>

              <div className="workflow-separation-note">
                <strong>Approbation ≠ confirmation.</strong>
                <span>Une demande peut être approuvée tout en restant Tentative; les deux concepts ne sont jamais fusionnés par l’interface.</span>
              </div>

              {approvalStateError && (
                <div className="plan-delta-unavailable">{approvalStateError}</div>
              )}

              {approvalState && (
                <div
                  className={`workflow-envelope-decision ${approvalState.envelope_decision === "REAPPROVAL_REQUIRED" ? "requires-approval" : ""}`}
                  data-testid="envelope-decision"
                >
                  <strong>{envelopeDecisionLabel(approvalState.envelope_decision)}</strong>
                  <span>
                    Décision backend : {approvalState.envelope_reason || "aucune raison"}.
                    {approvalState.candidate_matches_approved === false
                      ? " La proposition candidate diffère de l’autorisation active; l’ancien plan reste la référence tant qu’elle n’est pas approuvée."
                      : " La candidate correspond à l’autorisation approuvée active."}
                  </span>
                </div>
              )}

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
                    <div className="plan-delta-unavailable">
                      <span>{unavailableDeltaMessage(planDelta.reason)}</span>
                      {planDelta.diagnostics.length > 0 && (
                        <ul className="plan-delta-diagnostics" aria-label="Blocages du plan proposé">
                          {planDelta.diagnostics.map((diagnostic) => (
                            <li key={`${diagnostic.code}-${diagnostic.requirement_id ?? "global"}`}>
                              <strong>{diagnostic.code}</strong> — {diagnostic.message}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
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
                  <button type="button" className="primary-button" disabled={busy || hasUnsavedChanges} onClick={() => runAction("submit")}>
                    {pendingAction === "submit" ? "Soumission…" : actionLabel("submit")}
                  </button>
                )}
                {actions.includes("approve") && (
                  <button type="button" className="primary-button" disabled={busy || hasUnsavedChanges} onClick={() => runAction("approve")}>
                    {pendingAction === "approve" ? "Approbation…" : actionLabel("approve")}
                  </button>
                )}
                {actions.includes("correction") && (
                  <button type="button" className="secondary-button" disabled={busy || hasUnsavedChanges || !correctionComment.trim()} onClick={() => runAction("correction")}>
                    {pendingAction === "correction" ? "Envoi…" : actionLabel("correction")}
                  </button>
                )}
                {actions.includes("cancel") && (
                  <button type="button" className="secondary-button workflow-cancel" disabled={busy || hasUnsavedChanges} onClick={() => runAction("cancel")}>
                    {pendingAction === "cancel" ? "Annulation…" : actionLabel("cancel")}
                  </button>
                )}
              </div>

              <small className="workflow-authority-note">
                Les actions affichées proviennent de la projection backend canonique; FastAPI demeure l’autorité pour accepter ou refuser chaque commande.
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
