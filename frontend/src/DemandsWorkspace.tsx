import { useState } from "react";

import DemandPeriodsPage from "./DemandPeriodsPage";
import DemandSegmentsPage from "./DemandSegmentsPage";
import DemandWorkflowPage from "./DemandWorkflowPage";
import DemandsPage from "./DemandsPage";

type DemandWorkspaceView = "requests" | "segments" | "periods" | "workflow";

export default function DemandsWorkspace() {
  const [view, setView] = useState<DemandWorkspaceView>("requests");

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
        <button
          type="button"
          className={view === "segments" ? "active" : ""}
          onClick={() => setView("segments")}
        >
          Segments
        </button>
        <button
          type="button"
          className={view === "periods" ? "active" : ""}
          onClick={() => setView("periods")}
        >
          Périodes & alternatives
        </button>
        <button
          type="button"
          className={view === "workflow" ? "active" : ""}
          onClick={() => setView("workflow")}
        >
          Workflow
        </button>
      </nav>
      {view === "requests" ? (
        <DemandsPage />
      ) : view === "segments" ? (
        <DemandSegmentsPage />
      ) : view === "periods" ? (
        <DemandPeriodsPage />
      ) : (
        <DemandWorkflowPage />
      )}
    </div>
  );
}
