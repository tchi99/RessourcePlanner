import { useState } from "react";

import DemandPeriodsPage from "./DemandPeriodsPage";
import DemandsPage from "./DemandsPage";

type DemandWorkspaceView = "requests" | "periods";

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
          className={view === "periods" ? "active" : ""}
          onClick={() => setView("periods")}
        >
          Périodes & alternatives
        </button>
      </nav>
      {view === "requests" ? <DemandsPage /> : <DemandPeriodsPage />}
    </div>
  );
}
