import { useState } from "react";

import DemandsWorkspace from "./DemandsWorkspace";
import MediumTermPage from "./MediumTermPage";
import PlanningPage from "./PlanningPage";
import ProjectsPage from "./ProjectsPage";
import ResourcesPage from "./ResourcesPage";

type View = "planning" | "medium-term" | "demands" | "projects" | "resources" | "communications";

const navItems: Array<{ key: View; label: string; eyebrow: string }> = [
  { key: "planning", label: "Planning opérationnel", eyebrow: "Semaine" },
  { key: "medium-term", label: "Moyen terme", eyebrow: "Capacité" },
  { key: "demands", label: "Demandes", eyebrow: "Main-d’œuvre" },
  { key: "projects", label: "Projets", eyebrow: "Portefeuille" },
  { key: "resources", label: "Ressources", eyebrow: "Administration" },
  { key: "communications", label: "Communications", eyebrow: "À venir" },
];

function Placeholder({ view }: { view: View }) {
  const item = navItems.find((entry) => entry.key === view)!;
  return (
    <section className="placeholder-panel">
      <span className="eyebrow">{item.eyebrow}</span>
      <h2>{item.label}</h2>
      <p>
        Cette section fait partie du shell React V2. Elle sera branchée progressivement
        aux contrats FastAPI après la stabilisation du planning opérationnel.
      </p>
    </section>
  );
}

export default function App() {
  const [view, setView] = useState<View>("planning");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="app-shell">
      <aside className={`app-sidebar ${sidebarOpen ? "is-open" : ""}`}>
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">RP</div>
          <div>
            <strong>RessourcePlanner</strong>
            <span>Planification industrielle</span>
          </div>
        </div>

        <nav className="main-nav" aria-label="Navigation principale">
          {navItems.map((item) => (
            <button
              type="button"
              key={item.key}
              className={view === item.key ? "active" : ""}
              onClick={() => {
                setView(item.key);
                setSidebarOpen(false);
              }}
            >
              <span>{item.eyebrow}</span>
              <strong>{item.label}</strong>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span>Frontend V2</span>
          <strong>React + FastAPI</strong>
        </div>
      </aside>

      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Fermer la navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <div className="app-content">
        <header className="topbar">
          <button
            type="button"
            className="menu-button"
            onClick={() => setSidebarOpen((value) => !value)}
            aria-label="Ouvrir la navigation"
          >
            ☰
          </button>
          <div>
            <span className="topbar-context">RessourcePlanner V2</span>
            <strong>{navItems.find((item) => item.key === view)?.label}</strong>
          </div>
          <div className="topbar-status" title="Authentification Acumatica à venir">
            <span className="status-dot" />
            Mode développement
          </div>
        </header>

        <main className="main-content">
          {view === "planning" ? (
            <PlanningPage />
          ) : view === "medium-term" ? (
            <MediumTermPage onOpenDemands={() => setView("demands")} />
          ) : view === "demands" ? (
            <DemandsWorkspace />
          ) : view === "projects" ? (
            <ProjectsPage />
          ) : view === "resources" ? (
            <ResourcesPage />
          ) : (
            <Placeholder view={view} />
          )}
        </main>
      </div>
    </div>
  );
}
