import { useEffect, useState } from "react";

import {
  ApiError,
  type DemandDetailReadModel,
  getDemandDetail,
} from "./api";
import DemandHistoryPage from "./DemandHistoryPage";
import DemandPeriodsPage from "./DemandPeriodsPage";
import DemandWorkflowPage from "./DemandWorkflowPage";

function detailError(reason: unknown) {
  if (reason instanceof ApiError) {
    return `${reason.message}${reason.code ? ` (${reason.code})` : ""}`;
  }
  return reason instanceof Error ? reason.message : "Impossible de charger le détail de la demande.";
}

function hours(value: number) {
  return new Intl.NumberFormat("fr-CA", { maximumFractionDigits: 1 }).format(value);
}

export default function DemandDetail({
  demandNumber,
  onChanged,
  onDirtyChange,
  compact = false,
}: {
  demandNumber: string;
  onChanged?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  compact?: boolean;
}) {
  const [detail, setDetail] = useState<DemandDetailReadModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getDemandDetail(demandNumber, controller.signal)
      .then(setDetail)
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(detailError(reason));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [demandNumber, refreshKey]);

  function changed() {
    setRefreshKey((value) => value + 1);
    onChanged?.();
  }

  if (loading && !detail) {
    return <div className="demand-detail-loading">Chargement du contexte unifié…</div>;
  }

  if (error && !detail) {
    return <div className="error-panel"><strong>Détail indisponible.</strong><span>{error}</span></div>;
  }

  if (!detail) return null;

  const activeLines = detail.lines.filter((row) => row.line.active);
  const availableActions = detail.workflow.available_actions;
  const approval = detail.approval_state;

  return (
    <section className={`demand-detail-context ${compact ? "compact" : ""}`} data-demand-number={demandNumber}>
      <header className="demand-detail-context-header">
        <div>
          <span className="eyebrow">Contexte unifié</span>
          <h3>{detail.demand.number} · {detail.demand.project_number || "Sans projet"}</h3>
          <p>
            Version {detail.version} · {activeLines.length} besoin(s) ·
            {" "}{detail.materialized_plan.requirement_count} besoin(s) matérialisé(s)
          </p>
        </div>
        <div className="demand-detail-statuses">
          <span>{detail.demand.status}</span>
          {detail.policy.reapproval_required && <strong>Réapprobation requise</strong>}
        </div>
      </header>

      {error && <div className="error-panel"><span>{error}</span></div>}

      <div className="demand-detail-summary-grid">
        <article>
          <span>Plan actif</span>
          <strong>{hours(detail.materialized_plan.covered_hours)} / {hours(detail.materialized_plan.planned_hours)} h</strong>
          <small>{hours(detail.materialized_plan.locked_hours)} h verrouillées</small>
        </article>
        <article>
          <span>Autorisation</span>
          <strong>{approval?.approval_reference_status || "Aucune référence active"}</strong>
          <small>{detail.policy.envelope_decision || "Décision non disponible"}</small>
        </article>
        <article>
          <span>Actions disponibles</span>
          <strong>{availableActions.length}</strong>
          <small>{availableActions.length ? availableActions.join(" · ") : "Aucune action"}</small>
        </article>
      </div>

      {detail.diagnostics.length > 0 && (
        <details className="demand-detail-diagnostics">
          <summary>{detail.diagnostics.length} diagnostic(s) backend</summary>
          <ul>
            {detail.diagnostics.map((diagnostic) => <li key={diagnostic}>{diagnostic}</li>)}
          </ul>
        </details>
      )}

      <details className="demand-detail-section" open>
        <summary>
          <span>Périodes de travail</span>
          <small>Définir plusieurs périodes ou plusieurs fenêtres possibles par besoin.</small>
        </summary>
        <DemandPeriodsPage
          demandNumber={demandNumber}
          embedded
          onChanged={changed}
          onDirtyChange={onDirtyChange}
          canEdit={detail.policy.can_edit_periods}
        />
      </details>

      <details className="demand-detail-section">
        <summary>
          <span>Workflow et impact</span>
          <small>Actions autoritaires, autorisation active et aperçu plan actuel → plan proposé.</small>
        </summary>
        <DemandWorkflowPage
          demandNumber={demandNumber}
          embedded
          onChanged={changed}
        />
      </details>

      <details className="demand-detail-section">
        <summary>
          <span>Historique</span>
          <small>Chronologie auditée de cette demande, sans changer de contexte.</small>
        </summary>
        <DemandHistoryPage demandNumber={demandNumber} embedded />
      </details>
    </section>
  );
}
