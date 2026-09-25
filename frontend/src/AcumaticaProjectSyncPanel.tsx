import { useEffect, useState } from "react";

import {
  AcumaticaIntegrationStatus,
  ProjectSyncResult,
  getAcumaticaIntegrationStatus,
  syncAcumaticaProjects,
} from "./acumaticaIntegrationApi";


export default function AcumaticaProjectSyncPanel() {
  const [status, setStatus] = useState<AcumaticaIntegrationStatus | null>(null);
  const [result, setResult] = useState<ProjectSyncResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getAcumaticaIntegrationStatus(controller.signal)
      .then(setStatus)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "État Acumatica indisponible.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  async function synchronize() {
    if (syncing || !status?.configured) return;
    setSyncing(true);
    setError(null);
    setResult(null);
    try {
      setResult(await syncAcumaticaProjects());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "La synchronisation des projets a échoué.");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <section className="configuration-card">
      <div className="configuration-section-heading">
        <div>
          <span className="eyebrow">Bootstrap PO</span>
          <h3>Projets Acumatica</h3>
          <small>
            La synchronisation utilise le chemin OData canonique. L’ancien import Excel projets
            n’est pas le chemin recommandé pour initialiser un environnement de test.
          </small>
        </div>
        <strong>{loading ? "Vérification…" : status?.configured ? "Configuré" : "Non configuré"}</strong>
      </div>

      {!loading && !status?.configured && (
        <div className="error-panel">
          <strong>Configuration requise</strong>
          <span>Configurez les variables Acumatica du serveur avant de lancer la synchronisation.</span>
        </div>
      )}

      {error && (
        <div className="error-panel" aria-live="polite">
          <strong>Synchronisation interrompue</strong>
          <span>{error}</span>
          <span>Erreurs : 1. Aucune réussite partielle n’est présentée comme un import valide.</span>
        </div>
      )}

      {result && (
        <div className="configuration-status-grid" aria-live="polite">
          <div>
            <span className="eyebrow">Reçus</span>
            <strong>{result.received}</strong>
          </div>
          <div>
            <span className="eyebrow">Créés</span>
            <strong>{result.created}</strong>
          </div>
          <div>
            <span className="eyebrow">Mis à jour</span>
            <strong>{result.updated}</strong>
          </div>
          <div>
            <span className="eyebrow">Inchangés</span>
            <strong>{result.unchanged}</strong>
          </div>
          <div>
            <span className="eyebrow">Erreurs</span>
            <strong>0</strong>
          </div>
        </div>
      )}

      <div className="configuration-actions">
        <button
          className="primary-button"
          type="button"
          disabled={loading || syncing || !status?.configured}
          onClick={() => void synchronize()}
        >
          {syncing ? "Synchronisation…" : "Synchroniser les projets"}
        </button>
      </div>
    </section>
  );
}
