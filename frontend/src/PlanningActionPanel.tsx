import { useMemo, useState } from "react";

import {
  ApiError,
  PlanningActionReadModel,
  ResourceRecommendationReadModel,
  getResourceRecommendations,
} from "./api";
import { useAuth } from "./AuthContext";
import { assignSegment } from "./segments-api";

type Props = {
  actions: PlanningActionReadModel[];
  loading: boolean;
  onAssigned: () => void;
  onOpenDemands?: () => void;
};

function hours(value: number | null | undefined) {
  return new Intl.NumberFormat("fr-CA", {
    maximumFractionDigits: 1,
    minimumFractionDigits: Number(value ?? 0) % 1 ? 1 : 0,
  }).format(Number(value ?? 0));
}

function dateRange(action: PlanningActionReadModel) {
  return action.start_date === action.end_date
    ? action.start_date
    : `${action.start_date} → ${action.end_date}`;
}

function ActionCard({
  action,
  onRecommend,
  onOpenDemands,
}: {
  action: PlanningActionReadModel;
  onRecommend: (action: PlanningActionReadModel) => void;
  onOpenDemands?: () => void;
}) {
  const assignment = action.kind === "ASSIGNMENT";
  const task = [action.task_code, action.task_label].filter(Boolean).join(" — ");
  return (
    <article className={`planning-action-card action-${action.kind.toLowerCase()}`}>
      <div className="planning-action-card-heading">
        <div>
          <span className="planning-action-kicker">
            {assignment ? "Ressource à attribuer" : "Approbation requise"}
          </span>
          <strong>
            {action.project_number || "Projet"}
            {action.project_name ? ` — ${action.project_name}` : ""}
          </strong>
        </div>
        <strong>{hours(action.planned_hours)} h</strong>
      </div>

      <div className="planning-action-meta">
        {action.demand_number && <span>Demande {action.demand_number}</span>}
        {action.segment_id && <span>{action.segment_id}</span>}
        {task && <span>{task}</span>}
        <span>{dateRange(action)}</span>
        {action.required_competency && <span>Compétence : {action.required_competency}</span>}
        {action.priority && <span>Priorité : {action.priority}</span>}
        {action.confirmation && <span>{action.confirmation}</span>}
        {action.emergency_override_active && <span>⚠ Dérogation urgente</span>}
      </div>

      <div className="planning-action-buttons">
        {assignment && (
          <button type="button" className="primary-action" onClick={() => onRecommend(action)}>
            Trouver une ressource
          </button>
        )}
        {action.demand_number && onOpenDemands && (
          <button type="button" onClick={onOpenDemands}>
            Voir la demande
          </button>
        )}
      </div>
    </article>
  );
}

export default function PlanningActionPanel({
  actions,
  loading,
  onAssigned,
  onOpenDemands,
}: Props) {
  const { can } = useAuth();
  const canAssign = can("manage_planning");
  const [selectedAction, setSelectedAction] = useState<PlanningActionReadModel | null>(null);
  const [recommendations, setRecommendations] = useState<ResourceRecommendationReadModel[]>([]);
  const [recommendationLoading, setRecommendationLoading] = useState(false);
  const [recommendationError, setRecommendationError] = useState<string | null>(null);
  const [assigningResource, setAssigningResource] = useState<string | null>(null);

  const approvals = useMemo(
    () => actions.filter((action) => action.kind === "APPROVAL"),
    [actions],
  );
  const assignments = useMemo(
    () => actions.filter((action) => action.kind === "ASSIGNMENT"),
    [actions],
  );

  const openRecommendations = (action: PlanningActionReadModel) => {
    if (!action.segment_id) return;
    setSelectedAction(action);
    setRecommendations([]);
    setRecommendationError(null);
    setRecommendationLoading(true);
    getResourceRecommendations(action.segment_id)
      .then(setRecommendations)
      .catch((reason: unknown) => {
        if (reason instanceof ApiError) {
          setRecommendationError(`${reason.message}${reason.code ? ` (${reason.code})` : ""}`);
        } else {
          setRecommendationError(
            reason instanceof Error ? reason.message : "Impossible de calculer les recommandations.",
          );
        }
      })
      .finally(() => setRecommendationLoading(false));
  };

  const closeRecommendations = () => {
    if (assigningResource) return;
    setSelectedAction(null);
    setRecommendations([]);
    setRecommendationError(null);
  };

  const assign = async (candidate: ResourceRecommendationReadModel) => {
    if (!selectedAction?.segment_id || !canAssign) return;
    setAssigningResource(candidate.resource_id);
    setRecommendationError(null);
    try {
      await assignSegment(selectedAction.segment_id, candidate.resource_name);
      closeRecommendations();
      onAssigned();
    } catch (reason: unknown) {
      if (reason instanceof ApiError) {
        setRecommendationError(`${reason.message}${reason.code ? ` (${reason.code})` : ""}`);
      } else {
        setRecommendationError(reason instanceof Error ? reason.message : "Impossible d’assigner la ressource.");
      }
    } finally {
      setAssigningResource(null);
    }
  };

  return (
    <>
      <section className="planning-action-panel" aria-label="Éléments de planification à traiter">
        <div className="planning-action-panel-heading">
          <div>
            <span className="eyebrow">À traiter</span>
            <strong>Approbations et travaux à planifier</strong>
          </div>
          <div className="planning-action-counts">
            <span>{approvals.length} à approuver</span>
            <span>{assignments.length} à attribuer</span>
          </div>
        </div>

        {loading ? (
          <div className="planning-action-empty">Chargement des éléments à traiter…</div>
        ) : actions.length === 0 ? (
          <div className="planning-action-empty">Aucune action de planification dans cette fenêtre.</div>
        ) : (
          <div className="planning-action-columns">
            <div>
              <div className="planning-action-section-title">
                <strong>En attente d’approbation</strong>
                <span>{approvals.length}</span>
              </div>
              <div className="planning-action-list">
                {approvals.length > 0
                  ? approvals.map((action) => (
                    <ActionCard
                      key={`approval-${action.reference}`}
                      action={action}
                      onRecommend={openRecommendations}
                      onOpenDemands={onOpenDemands}
                    />
                  ))
                  : <div className="planning-action-empty compact">Aucune demande à approuver.</div>}
              </div>
            </div>

            <div>
              <div className="planning-action-section-title">
                <strong>Travaux à planifier</strong>
                <span>{assignments.length}</span>
              </div>
              <div className="planning-action-list">
                {assignments.length > 0
                  ? assignments.map((action) => (
                    <ActionCard
                      key={`assignment-${action.reference}`}
                      action={action}
                      onRecommend={openRecommendations}
                      onOpenDemands={onOpenDemands}
                    />
                  ))
                  : <div className="planning-action-empty compact">Tous les besoins sont attribués.</div>}
              </div>
            </div>
          </div>
        )}
      </section>

      {selectedAction && (
        <div className="recommendation-backdrop" role="presentation" onMouseDown={closeRecommendations}>
          <section
            className="recommendation-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Trouver une ressource"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="recommendation-heading">
              <div>
                <span className="eyebrow">Trouver une ressource</span>
                <h2>
                  {selectedAction.project_number || "Projet"}
                  {selectedAction.project_name ? ` — ${selectedAction.project_name}` : ""}
                </h2>
                <p>
                  {hours(selectedAction.planned_hours)} h · {dateRange(selectedAction)}
                  {selectedAction.required_competency
                    ? ` · Compétence : ${selectedAction.required_competency}`
                    : ""}
                </p>
              </div>
              <button type="button" onClick={closeRecommendations} disabled={Boolean(assigningResource)}>
                Fermer
              </button>
            </div>

            <p className="recommendation-explainer">
              Classement backend inspiré de NiceGUI V1.6 : compétence, classe puis capacité prudente sur toute
              la fenêtre du segment. La capacité prudente soustrait la charge confirmée et tentative.
            </p>

            {recommendationError && <div className="error-panel">{recommendationError}</div>}

            {recommendationLoading ? (
              <div className="planning-action-empty">Calcul des disponibilités…</div>
            ) : recommendations.length === 0 ? (
              <div className="planning-action-empty">Aucune ressource planifiable trouvée.</div>
            ) : (
              <div className="recommendation-list">
                {recommendations.map((candidate) => (
                  <article
                    className={`recommendation-card ${candidate.recommended ? "is-recommended" : ""}`}
                    key={candidate.resource_id}
                  >
                    <div className="recommendation-card-heading">
                      <div>
                        <strong>
                          {candidate.resource_name}
                          {candidate.recommended ? " · Recommandé" : ""}
                        </strong>
                        <span>{candidate.resource_class || "Non classé"}</span>
                      </div>
                      <span className="rank-pill">#{candidate.rank}</span>
                    </div>

                    <div className="recommendation-signals">
                      <span className={candidate.competency_match ? "signal-good" : "signal-warn"}>
                        {candidate.competency_match
                          ? "Compétence correspondante"
                          : "Compétence requise non attribuée"}
                      </span>
                      {candidate.required_class && (
                        <span className={candidate.class_match ? "signal-good" : "signal-muted"}>
                          {candidate.class_match
                            ? `Classe ${candidate.required_class}`
                            : `Classe différente de ${candidate.required_class}`}
                        </span>
                      )}
                    </div>

                    <div className="recommendation-capacity">
                      <span>{hours(candidate.prudent_free)} h libres prudentes</span>
                      <span>{hours(candidate.free_after_confirmed)} h après confirmés</span>
                      <span>{hours(candidate.tentative_hours)} h tentatives</span>
                      <span>{hours(candidate.capacity_hours)} h capacité</span>
                    </div>

                    {candidate.overtime_needed > 0 && (
                      <small className="recommendation-warning">
                        Environ {hours(candidate.overtime_needed)} h ne tiennent pas dans la capacité prudente.
                      </small>
                    )}

                    <button
                      type="button"
                      className="primary-action"
                      disabled={!canAssign || Boolean(assigningResource)}
                      onClick={() => void assign(candidate)}
                      title={!canAssign ? "Permission manage_planning requise" : undefined}
                    >
                      {assigningResource === candidate.resource_id ? "Assignation…" : "Assigner"}
                    </button>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
