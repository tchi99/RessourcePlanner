import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  DemandReadModel,
  ResourceReadModel,
  SegmentReadModel,
  getDemands,
  getResources,
} from "./api";
import { getSegments } from "./segments-api";
import SegmentEditor from "./SegmentEditor";

function normalize(value: string | null | undefined) {
  return (value ?? "").trim().toLocaleLowerCase("fr-CA");
}

function messageFromError(reason: unknown) {
  if (reason instanceof ApiError) {
    return `${reason.message}${reason.code ? ` (${reason.code})` : ""}`;
  }
  return reason instanceof Error ? reason.message : "Impossible de charger les segments.";
}

function segmentSearchText(segment: SegmentReadModel) {
  return normalize([
    segment.segment_id,
    segment.demand_number,
    segment.project_number,
    segment.project_name,
    segment.resource_name,
    segment.status,
    segment.description,
    segment.required_competency,
    segment.planning_type,
    segment.priority,
  ].filter(Boolean).join(" "));
}

function hours(value: number | null | undefined) {
  return new Intl.NumberFormat("fr-CA", { maximumFractionDigits: 1 }).format(Number(value ?? 0));
}

function SegmentCard({ segment, onOpen }: { segment: SegmentReadModel; onOpen: () => void }) {
  const cancelled = normalize(segment.status).startsWith("annul");
  return (
    <button type="button" className={`segment-card ${cancelled ? "segment-card-cancelled" : ""}`} onClick={onOpen}>
      <div className="segment-card-heading">
        <div>
          <span className="segment-card-id">{segment.segment_id}</span>
          <strong>{segment.required_competency || segment.description || "Besoin ressource"}</strong>
        </div>
        <strong>{hours(segment.planned_hours)} h</strong>
      </div>
      <div className="segment-card-meta">
        <span>{segment.start_date || "—"}{segment.end_date && segment.end_date !== segment.start_date ? ` → ${segment.end_date}` : ""}</span>
        <span>{segment.status || "—"}</span>
        <span>{segment.planning_type || "—"}</span>
        {segment.outside_standard_hours && <span>Hors horaire</span>}
      </div>
      <div className="segment-card-footer">
        <span>{segment.resource_name ? `Assigné : ${segment.resource_name}` : "Non assigné"}</span>
        <span>{segment.confirmation || "Confirmation héritée"}</span>
      </div>
    </button>
  );
}

export default function DemandSegmentsPage() {
  const [demands, setDemands] = useState<DemandReadModel[]>([]);
  const [segments, setSegments] = useState<SegmentReadModel[]>([]);
  const [resources, setResources] = useState<ResourceReadModel[]>([]);
  const [selectedDemandNumber, setSelectedDemandNumber] = useState<string | null>(null);
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [includeCancelled, setIncludeCancelled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      getDemands(controller.signal),
      getSegments(true, controller.signal),
      getResources(true, controller.signal),
    ])
      .then(([demandRows, segmentRows, resourceRows]) => {
        setDemands(demandRows);
        setSegments(segmentRows);
        setResources(resourceRows);
        setSelectedDemandNumber((current) => {
          if (current && demandRows.some((row) => row.number === current)) return current;
          return demandRows[0]?.number ?? null;
        });
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(messageFromError(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refreshKey]);

  const selectedDemand = useMemo(
    () => demands.find((row) => row.number === selectedDemandNumber) ?? null,
    [demands, selectedDemandNumber],
  );

  const visibleDemands = useMemo(() => {
    const query = normalize(search);
    if (!query) return demands;
    return demands.filter((demand) => normalize([
      demand.number,
      demand.project_number,
      demand.project_name,
      demand.client,
      demand.status,
      demand.required_competencies,
    ].filter(Boolean).join(" ")).includes(query));
  }, [demands, search]);

  const selectedSegments = useMemo(() => {
    const query = normalize(search);
    return segments
      .filter((segment) => segment.demand_number === selectedDemandNumber)
      .filter((segment) => includeCancelled || !normalize(segment.status).startsWith("annul"))
      .filter((segment) => !query || segmentSearchText(segment).includes(query) || selectedDemand && normalize([
        selectedDemand.number,
        selectedDemand.project_number,
        selectedDemand.project_name,
      ].filter(Boolean).join(" ")).includes(query))
      .sort((left, right) => {
        const leftDate = left.start_date ?? "9999-12-31";
        const rightDate = right.start_date ?? "9999-12-31";
        return leftDate.localeCompare(rightDate) || left.segment_id.localeCompare(right.segment_id, "fr-CA");
      });
  }, [segments, selectedDemandNumber, includeCancelled, search, selectedDemand]);

  const totalHours = selectedSegments.reduce((sum, segment) => sum + Number(segment.planned_hours || 0), 0);

  function createForSelectedDemand() {
    if (!selectedDemand) return;
    setEditingSegmentId(null);
    setEditorOpen(true);
  }

  function openSegment(segmentId: string) {
    setEditingSegmentId(segmentId);
    setEditorOpen(true);
  }

  return (
    <section className="demand-segments-page">
      <div className="page-heading segments-heading">
        <div>
          <span className="eyebrow">Main-d’œuvre</span>
          <h1>Segments / besoins ressources</h1>
          <p>Le segment décrit le besoin à planifier. Les quarts représentent ensuite les affectations opérationnelles générées ou verrouillées.</p>
        </div>
        <button type="button" className="primary-button" onClick={createForSelectedDemand} disabled={!selectedDemand || loading}>
          + Nouveau segment
        </button>
      </div>

      {error && <div className="error-panel"><strong>Chargement impossible.</strong><span>{error}</span></div>}

      <div className="segment-filter-bar">
        <label>
          <span>Recherche</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Demande, projet, segment, ressource…" />
        </label>
        <label className="checkbox-field segment-cancelled-toggle">
          <input type="checkbox" checked={includeCancelled} onChange={(event) => setIncludeCancelled(event.target.checked)} />
          <span>Afficher les segments annulés</span>
        </label>
      </div>

      <div className="segments-workspace">
        <aside className="segment-demand-list-panel">
          <div className="segment-demand-list-heading">
            <strong>{loading ? "Chargement…" : `${visibleDemands.length} demande(s)`}</strong>
            <span>{demands.length} au total</span>
          </div>
          <div className="segment-demand-list">
            {!loading && visibleDemands.length === 0 && <div className="segment-empty">Aucune demande ne correspond à la recherche.</div>}
            {visibleDemands.map((demand) => {
              const count = segments.filter((segment) => segment.demand_number === demand.number && !normalize(segment.status).startsWith("annul")).length;
              return (
                <button
                  type="button"
                  key={demand.number}
                  className={`segment-demand-card ${demand.number === selectedDemandNumber ? "selected" : ""}`}
                  onClick={() => setSelectedDemandNumber(demand.number)}
                >
                  <div><strong>{demand.number}</strong><span>{demand.status || "—"}</span></div>
                  <span>{demand.project_number || "Projet"}{demand.project_name ? ` — ${demand.project_name}` : ""}</span>
                  <small>{count} segment(s) actif(s)</small>
                </button>
              );
            })}
          </div>
        </aside>

        <div className="segment-detail-panel">
          {selectedDemand ? (
            <>
              <div className="segment-detail-heading">
                <div>
                  <span className="eyebrow">Demande {selectedDemand.number}</span>
                  <h2>{selectedDemand.project_number || "Projet"}{selectedDemand.project_name ? ` — ${selectedDemand.project_name}` : ""}</h2>
                  <p>{selectedDemand.required_competencies || selectedDemand.description || "Aucune description de besoin."}</p>
                </div>
                <div className="segment-summary-metrics">
                  <div><span>Segments affichés</span><strong>{selectedSegments.length}</strong></div>
                  <div><span>Heures prévues</span><strong>{hours(totalHours)} h</strong></div>
                </div>
              </div>

              <div className="segment-demand-context">
                <span>Fenêtre demandée : {selectedDemand.desired_start || "—"}{selectedDemand.desired_end ? ` → ${selectedDemand.desired_end}` : ""}</span>
                <span>Ressources : {selectedDemand.resource_count || 1}</span>
                <span>Priorité : {selectedDemand.priority || "—"}</span>
                <span>Confirmation : {selectedDemand.confirmation || "—"}</span>
              </div>

              {selectedSegments.length > 0 ? (
                <div className="segment-list">
                  {selectedSegments.map((segment) => <SegmentCard segment={segment} onOpen={() => openSegment(segment.segment_id)} key={segment.segment_id} />)}
                </div>
              ) : (
                <div className="segment-empty segment-empty-large">
                  <strong>Aucun segment pour cette demande.</strong>
                  <span>Crée un besoin ressource lorsque la demande doit être transformée en plan opérationnel.</span>
                  <button type="button" className="secondary-button" onClick={createForSelectedDemand}>Créer le premier segment</button>
                </div>
              )}
            </>
          ) : (
            <div className="segment-empty segment-empty-large">Sélectionne une demande pour consulter ses besoins ressources.</div>
          )}
        </div>
      </div>

      <SegmentEditor
        open={editorOpen}
        segmentId={editingSegmentId}
        demand={selectedDemand}
        resources={resources}
        onClose={() => setEditorOpen(false)}
        onSaved={() => {
          setEditorOpen(false);
          setEditingSegmentId(null);
          setRefreshKey((value) => value + 1);
        }}
      />
    </section>
  );
}
