import { useViewScope } from "./ViewScopeContext";

export default function ViewScopeSelector() {
  const { context, scope, loading, error, setScope } = useViewScope();

  if (loading) {
    return <div className="view-scope-selector is-loading">Périmètre…</div>;
  }
  if (error) {
    return <div className="view-scope-selector is-error">Vue globale</div>;
  }
  if (!context || context.view_policy.available_scopes.length < 2) return null;

  return (
    <div className="view-scope-selector" role="group" aria-label="Périmètre d’affichage">
      <span>Affichage</span>
      <button
        type="button"
        className={scope === "mine" ? "active" : ""}
        onClick={() => setScope("mine")}
      >
        Mon périmètre
      </button>
      <button
        type="button"
        className={scope === "global" ? "active" : ""}
        onClick={() => setScope("global")}
      >
        Vue globale
      </button>
    </div>
  );
}
