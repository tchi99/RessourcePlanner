import { useMemo, useState } from "react";

import { useAuth } from "./AuthContext";
import DemandsWorkspace from "./DemandsWorkspace";
import MediumTermPage from "./MediumTermPage";
import PlanningPage from "./PlanningPage";
import ProjectsPage from "./ProjectsPage";
import ResourcesPage from "./ResourcesPage";

type View = "planning" | "medium-term" | "demands" | "projects" | "resources" | "communications";

type NavItem = { key: View; label: string; eyebrow: string; permission?: string };

const navItems: NavItem[] = [
  { key: "planning", label: "Planning opérationnel", eyebrow: "Semaine" },
  { key: "medium-term", label: "Moyen terme", eyebrow: "Capacité" },
  { key: "demands", label: "Demandes", eyebrow: "Main-d’œuvre" },
  { key: "projects", label: "Projets", eyebrow: "Portefeuille" },
  { key: "resources", label: "Ressources", eyebrow: "Administration", permission: "manage_resources" },
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
  const {
    principal,
    loading: authLoading,
    error: authError,
    authenticationRequired,
    can,
    login,
    logout,
  } = useAuth();
  const [view, setView] = useState<View>("planning");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const visibleNavItems = useMemo(
    () => navItems.filter((item) => !item.permission || can(item.permission)),
    [can],
  );

  if (authLoading) {
    return (
      <main className="main-content">
        <section className="placeholder-panel">
          <span className="eyebrow">Authentification</span>
          <h2>Chargement de votre session…</h2>
        </section>
      </main>
    );
  }

  if (authenticationRequired || (!principal && !authError)) {
    return (
      <main className="main-content">
        <section className="placeholder-panel">
          <span className="eyebrow">Authentification</span>
          <h2>Connexion requise</h2>
          <p>Votre session RessourcePlanner est absente ou expirée.</p>
          <div className="week-navigation">
            <button type="button" onClick={login}>Se connecter avec Acumatica</button>
          </div>
        </section>
      </main>
    );
  }

  if (authError || !principal) {
    return (
      <main className="main-content">
        <section className="error-panel">
          <strong>Impossible d’ouvrir la session RessourcePlanner.</strong>
          <span>{authError || "Aucune identité active n’a été retournée par le serveur."}</span>
          <small>Les permissions sont déterminées par FastAPI; React ne peut pas contourner cette étape.</small>
        </section>
      </main>
    );
  }

  const currentItem = navItems.find((item) => item.key === view);

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
          {visibleNavItems.map((item) => (
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
          <span>{principal.display_name}</span>
          <strong>{principal.roles.join(" · ")}</strong>
          {principal.auth_mode === "oidc" && (
            <button type="button" onClick={() => void logout().catch(() => undefined)}>
              Déconnexion
            </button>
          )}
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
            <strong>{currentItem?.label}</strong>
          </div>
          <div className="topbar-status" title={`Mode d’authentification: ${principal.auth_mode}`}>
            <span className="status-dot" />
            {principal.display_name}
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
          ) : view === "resources" && can("manage_resources") ? (
            <ResourcesPage />
          ) : (
            <Placeholder view={view} />
          )}
        </main>
      </div>
    </div>
  );
}
