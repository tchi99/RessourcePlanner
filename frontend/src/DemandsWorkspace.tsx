import { useEffect, useState } from "react";

import { useAuth } from "./AuthContext";
import DemandHistoryPage from "./DemandHistoryPage";
import DemandPeriodsPage from "./DemandPeriodsPage";
import DemandSegmentsPage from "./DemandSegmentsPage";
import DemandWorkflowPage from "./DemandWorkflowPage";
import DemandsPage from "./DemandsPage";
import EmergencyOverridePage from "./EmergencyOverridePage";

type DemandWorkspaceView = "requests" | "segments" | "periods" | "workflow" | "emergency" | "history";

export default function DemandsWorkspace() {
  const { can } = useAuth();
  const canManageDemands = can("manage_demands");
  const canManagePlanning = can("manage_planning");
  const canApprove = can("approve_demands");
  const [view, setView] = useState<DemandWorkspaceView>("requests");

  useEffect(() => {
    if (view === "segments" && !canManagePlanning) setView("requests");
    if (view === "periods" && !canManageDemands) setView("requests");
    if (view === "workflow" && !canManageDemands && !canApprove) setView("requests");
    if (view === "emergency" && !canApprove) setView("requests");
  }, [view, canManagePlanning, canManageDemands, canApprove]);

  return (
    <div className="demands-workspace-shell">
      <nav className="demands-subnav" aria-label="Sections des demandes">
        <button
          type="button"
          className={view === "requests" ? "active" : ""}
          onClick={() => setView("requests")}
        >
          Demandes
        </button>
        {canManagePlanning && (
          <button
            type="button"
            className={view === "segments" ? "active" : ""}
            onClick={() => setView("segments")}
          >
            Segments
          </button>
        )}
        {canManageDemands && (
          <button
            type="button"
            className={view === "periods" ? "active" : ""}
            onClick={() => setView("periods")}
          >
            Périodes & alternatives
          </button>
        )}
        {(canManageDemands || canApprove) && (
          <button
            type="button"
            className={view === "workflow" ? "active" : ""}
            onClick={() => setView("workflow")}
          >
            Workflow
          </button>
        )}
        {canApprove && (
          <button
            type="button"
            className={view === "emergency" ? "active" : ""}
            onClick={() => setView("emergency")}
          >
            Urgence
          </button>
        )}
        <button
          type="button"
          className={view === "history" ? "active" : ""}
          onClick={() => setView("history")}
        >
          Historique
        </button>
      </nav>
      {view === "requests" ? (
        <DemandsPage />
      ) : view === "segments" ? (
        <DemandSegmentsPage />
      ) : view === "periods" ? (
        <DemandPeriodsPage />
      ) : view === "workflow" ? (
        <DemandWorkflowPage />
      ) : view === "emergency" ? (
        <EmergencyOverridePage />
      ) : (
        <DemandHistoryPage />
      )}
    </div>
  );
}