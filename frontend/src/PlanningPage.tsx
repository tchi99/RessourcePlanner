import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  PendingDemandLoadReadModel,
  PlanningSnapshotReadModel,
  ResourceReadModel,
  ShiftReadModel,
  getPlanningSnapshot,
} from "./api";
import {
  addDays,
  formatDay,
  formatWeekRange,
  isToday,
  sameIsoDate,
  startOfWeek,
  toIsoDate,
  weekDays,
} from "./dates";
import ShiftEditor from "./ShiftEditor";

type ConfirmationFilter = "all" | "confirmed" | "tentative";

function normalize(value: string | null | undefined) {
  return (value ?? "").trim().toLocaleLowerCase("fr-CA");
}

function confirmationKind(value: string | null | undefined): "confirmed" | "tentative" | "unknown" {
  const normalized = normalize(value);
  if (normalized.startsWith("confirm")) return "confirmed";
  if (normalized.startsWith("tent")) return "tentative";
  return "unknown";
}

function confirmationLabel(value: string | null | undefined) {
  const kind = confirmationKind(value);
  if (kind === "confirmed") return "Confirmée";
  if (kind === "tentative") return "Tentative";
  return value || "Non précisée";
}

function hours(value: number | null | undefined) {
  return new Intl.NumberFormat("fr-CA", {
    maximumFractionDigits: 1,
    minimumFractionDigits: Number(value ?? 0) % 1 ? 1 : 0,
  }).format(Number(value ?? 0));
}

function shiftText(shift: ShiftReadModel) {
  return normalize([
    shift.resource_name,
    shift.project_number,
    shift.project_name,
    shift.demand_number,
    shift.project_manager,
    shift.requester,
    shift.note,
  ].filter(Boolean).join(" "));
}

function pendingText(load: PendingDemandLoadReadModel) {
  return normalize([
    load.demand_number,
    load.project_number,
    load.project_name,
    load.required_competencies,
    load.proposed_resource,
  ].filter(Boolean).join(" "));
}

function ProjectLabel({ number, name }: { number: string | null; name: string | null }) {
  return (
    <>
      <strong>{number || "Projet"}</strong>
      {name && <span>{name}</span>}
    </>
  );
}

function ShiftCard({ shift, onEdit }: { shift: ShiftReadModel; onEdit: (shift: ShiftReadModel) => void }) {
  const confirmation = confirmationKind(shift.confirmation);
  const meta = [
    shift.allocation_type,
    shift.source !== "AUTO" ? shift.source : null,
    shift.locked ? "Verrouillé" : null,
    shift.outside_standard_hours ? "Hors horaire" : null,
  ].filter(Boolean);

  return (
    <button
      type="button"
      className={`shift-card shift-${confirmation} ${shift.outside_standard_hours ? "shift-outside" : ""}`}
      onClick={() => onEdit(shift)}
      aria-label={`Modifier le quart ${shift.project_number || shift.project_name || shift.allocation_id}, ${hours(shift.hours)} heures`}
      title={[
        "Cliquer pour modifier",
        shift.project_name,
        shift.demand_number ? `Demande ${shift.demand_number}` : null,
        shift.project_manager ? `Responsable: ${shift.project_manager}` : null,
        shift.requester ? `Demandeur: ${shift.requester}` : null,
        shift.note,
      ].filter(Boolean).join("\n")}
    >
      <div className="shift-card-heading">
        <div className="shift-project">
          <ProjectLabel number={shift.project_number} name={shift.project_name} />
        </div>
        <strong className="shift-hours">{hours(shift.hours)} h</strong>
      </div>
      <div className="shift-badges">
        <span className={`confirmation-badge confirmation-${confirmation}`}>
          {confirmationLabel(shift.confirmation)}
        </span>
        {shift.demand_number && <span>#{shift.demand_number}</span>}
      </div>
      {meta.length > 0 && <small>{meta.join(" · ")}</small>}
    </button>
  );
}

function PendingLoadCard({ load }: { load: PendingDemandLoadReadModel }) {
  const proposed = load.projected_hours ?? load.window_hours;
  const replacement = normalize(load.mode) === "replacement";
  const dateLabel = load.start_date === load.end_date
    ? load.start_date
    : `${load.start_date} → ${load.end_date}`;

  return (
    <article className={`pending-card ${replacement ? "pending-replacement" : ""}`}>
      <div className="pending-card-heading">
        <div>
          <span className="pending-kicker">
            {replacement ? "Modification en attente" : "Charge potentielle"}
          </span>
          <ProjectLabel number={load.project_number} name={load.project_name} />
        </div>
        <strong>{hours(proposed)} h</strong>
      </div>
      <div className="pending-meta">
        <span>Demande {load.demand_number}</span>
        <span>{dateLabel}</span>
        {load.required_competencies && <span>{load.required_competencies}</span>}
        {load.proposed_resource && <span>Proposé : {load.proposed_resource}</span>}
      </div>
      {replacement && (
        <div className="pending-delta">
          <span>Plan actuel : {hours(load.current_plan_hours)} h</span>
          {load.delta_hours != null && (
            <strong className={load.delta_hours > 0 ? "positive-delta" : load.delta_hours < 0 ? "negative-delta" : ""}>
              Delta {load.delta_hours > 0 ? "+" : ""}{hours(load.delta_hours)} h
            </strong>
          )}
        </div>
      )}
    </article>
  );
}

function ResourceRow({
  resource,
  days,
  shifts,
  onEditShift,
}: {
  resource: ResourceReadModel;
  days: Date[];
  shifts: ShiftReadModel[];
  onEditShift: (shift: ShiftReadModel) => void;
}) {
  const total = shifts.reduce((sum, shift) => sum + Number(shift.hours || 0), 0);

  return (
    <div className="resource-row">
      <div className="resource-cell resource-identity">
        <strong>{resource.name}</strong>
        <span>{resource.competencies || resource.resource_class || "Ressource"}</span>
        <small>{hours(total)} h affichées</small>
      </div>
      {days.map((day) => {
        const dayShifts = shifts.filter((shift) => sameIsoDate(shift.work_date, day));
        return (
          <div className={`resource-cell planning-day-cell ${isToday(day) ? "today-column" : ""}`} key={toIsoDate(day)}>
            {dayShifts.length > 0
              ? dayShifts.map((shift) => <ShiftCard shift={shift} onEdit={onEditShift} key={shift.allocation_id} />)
              : <span className="empty-day">—</span>}
          </div>
        );
      })}
    </div>
  );
}

export default function PlanningPage() {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [snapshot, setSnapshot] = useState<PlanningSnapshotReadModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("all");
  const [confirmation, setConfirmation] = useState<ConfirmationFilter>("all");
  const [editingShift, setEditingShift] = useState<ShiftReadModel | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const days = useMemo(() => weekDays(weekStart), [weekStart]);
  const start = toIsoDate(weekStart);
  const end = toIsoDate(addDays(weekStart, 6));

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getPlanningSnapshot(start, end, controller.signal)
      .then(setSnapshot)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        if (reason instanceof ApiError) {
          setError(`${reason.message}${reason.code ? ` (${reason.code})` : ""}`);
          return;
        }
        setError(reason instanceof Error ? reason.message : "Impossible de charger le planning.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [start, end, refreshKey]);

  const projectOptions = useMemo(() => {
    if (!snapshot) return [];
    const values = new Map<string, string>();
    [...snapshot.shifts, ...snapshot.pending_loads].forEach((item) => {
      if (!item.project_number) return;
      values.set(item.project_number, item.project_name
        ? `${item.project_number} — ${item.project_name}`
        : item.project_number);
    });
    return [...values.entries()].sort((left, right) => left[1].localeCompare(right[1], "fr-CA"));
  }, [snapshot]);

  const query = normalize(search);

  const shiftsPassingGlobalFilters = useMemo(() => {
    if (!snapshot) return [];
    return snapshot.shifts.filter((shift) => {
      if (project !== "all" && shift.project_number !== project) return false;
      if (confirmation !== "all" && confirmationKind(shift.confirmation) !== confirmation) return false;
      return true;
    });
  }, [snapshot, project, confirmation]);

  const visibleResourceGroups = useMemo(() => {
    if (!snapshot) return [];
    const groups = new Map<string, Array<{ resource: ResourceReadModel; shifts: ShiftReadModel[] }>>();
    const restrictiveFilter = project !== "all" || confirmation !== "all" || Boolean(query);

    [...snapshot.resources]
      .sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name, "fr-CA"))
      .forEach((resource) => {
        const resourceMatches = !query || normalize(`${resource.name} ${resource.resource_class ?? ""} ${resource.competencies ?? ""}`).includes(query);
        const shifts = shiftsPassingGlobalFilters.filter((shift) => {
          if (shift.resource_id !== resource.id) return false;
          if (!query || resourceMatches) return true;
          return shiftText(shift).includes(query);
        });
        if (restrictiveFilter && !resourceMatches && shifts.length === 0) return;
        if ((project !== "all" || confirmation !== "all") && shifts.length === 0) return;
        const className = resource.resource_class || "Non classé";
        const entries = groups.get(className) ?? [];
        entries.push({ resource, shifts });
        groups.set(className, entries);
      });

    return [...groups.entries()].sort((left, right) => left[0].localeCompare(right[0], "fr-CA"));
  }, [snapshot, shiftsPassingGlobalFilters, project, confirmation, query]);

  const visiblePendingLoads = useMemo(() => {
    if (!snapshot) return [];
    return snapshot.pending_loads.filter((load) => {
      if (project !== "all" && load.project_number !== project) return false;
      if (query && !pendingText(load).includes(query)) return false;
      if (confirmation !== "all" && confirmationKind(load.confirmation) !== confirmation) return false;
      return true;
    });
  }, [snapshot, project, confirmation, query]);

  const visibleShiftHours = shiftsPassingGlobalFilters
    .filter((shift) => !query || shiftText(shift).includes(query) || snapshot?.resources.some(
      (resource) => resource.id === shift.resource_id && normalize(`${resource.name} ${resource.resource_class ?? ""}`).includes(query),
    ))
    .reduce((sum, shift) => sum + Number(shift.hours || 0), 0);

  return (
    <section className="planning-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Planification opérationnelle</span>
          <h1>Semaine du {formatWeekRange(weekStart)}</h1>
          <p>Planning Web V2 alimenté directement par le snapshot canonique FastAPI. Clique sur un quart pour le modifier.</p>
        </div>
        <div className="week-navigation" role="group" aria-label="Navigation par semaine">
          <button type="button" onClick={() => setWeekStart((value) => addDays(value, -7))}>← Précédente</button>
          <button type="button" onClick={() => setWeekStart(startOfWeek(new Date()))}>Aujourd’hui</button>
          <button type="button" onClick={() => setWeekStart((value) => addDays(value, 7))}>Suivante →</button>
        </div>
      </div>

      <div className="metric-grid">
        <article>
          <span>Charge ferme</span>
          <strong>{snapshot ? `${hours(snapshot.firm_hours)} h` : "—"}</strong>
          <small>Quarts confirmés dans la fenêtre</small>
        </article>
        <article>
          <span>Charge potentielle</span>
          <strong>{snapshot ? `${hours(snapshot.potential_hours)} h` : "—"}</strong>
          <small>Tentatif + demandes additives</small>
        </article>
        <article>
          <span>Remplacements proposés</span>
          <strong>{snapshot ? `${hours(snapshot.replacement_proposal_hours)} h` : "—"}</strong>
          <small>Scénarios non additionnés au plan</small>
        </article>
        <article>
          <span>Quarts affichés</span>
          <strong>{snapshot ? `${hours(visibleShiftHours)} h` : "—"}</strong>
          <small>{snapshot ? `${shiftsPassingGlobalFilters.length} quart(s) avant recherche` : "Chargement…"}</small>
        </article>
      </div>

      <div className="filter-bar">
        <label className="search-field">
          <span>Recherche</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Ressource, projet, demande…"
          />
        </label>
        <label>
          <span>Projet</span>
          <select value={project} onChange={(event) => setProject(event.target.value)}>
            <option value="all">Tous les projets</option>
            {projectOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select>
        </label>
        <label>
          <span>Confirmation</span>
          <select value={confirmation} onChange={(event) => setConfirmation(event.target.value as ConfirmationFilter)}>
            <option value="all">Confirmée + Tentative</option>
            <option value="confirmed">Confirmée</option>
            <option value="tentative">Tentative</option>
          </select>
        </label>
      </div>

      {error && (
        <div className="error-panel">
          <strong>Le planning n’a pas pu être chargé.</strong>
          <span>{error}</span>
          <small>Vérifie que FastAPI fonctionne sur le port 8000 et que la base locale est migrée.</small>
        </div>
      )}

      <div className="planning-layout">
        <div className="planning-board-panel">
          <div className="planning-board-toolbar">
            <div>
              <strong>Ressources et quarts</strong>
              <span>{loading ? "Actualisation…" : `${visibleResourceGroups.reduce((sum, [, rows]) => sum + rows.length, 0)} ressource(s)`}</span>
            </div>
            <div className="legend">
              <span><i className="legend-dot confirmed" />Confirmée</span>
              <span><i className="legend-dot tentative" />Tentative</span>
              <span><i className="legend-dot outside" />Hors horaire</span>
            </div>
          </div>

          <div className={`planning-board-scroll ${loading ? "is-loading" : ""}`}>
            <div className="planning-grid">
              <div className="planning-header resource-header">Ressource</div>
              {days.map((day) => (
                <div className={`planning-header day-header ${isToday(day) ? "today-column" : ""}`} key={toIsoDate(day)}>
                  <span>{formatDay(day)}</span>
                  {isToday(day) && <small>Aujourd’hui</small>}
                </div>
              ))}

              {!loading && visibleResourceGroups.length === 0 && (
                <div className="planning-empty">Aucune ressource ou aucun quart ne correspond aux filtres.</div>
              )}

              {visibleResourceGroups.map(([className, rows]) => (
                <div className="resource-group" key={className}>
                  <div className="resource-group-heading">
                    <strong>{className}</strong>
                    <span>{rows.length} ressource(s)</span>
                  </div>
                  {rows.map(({ resource, shifts }) => (
                    <ResourceRow
                      resource={resource}
                      days={days}
                      shifts={shifts}
                      onEditShift={setEditingShift}
                      key={resource.id}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside className="pending-panel">
          <div className="pending-panel-heading">
            <div>
              <span className="eyebrow">À anticiper</span>
              <strong>Demandes en attente</strong>
            </div>
            <span className="count-pill">{visiblePendingLoads.length}</span>
          </div>
          {loading && !snapshot ? (
            <div className="pending-empty">Chargement…</div>
          ) : visiblePendingLoads.length > 0 ? (
            <div className="pending-list">
              {visiblePendingLoads.map((load) => (
                <PendingLoadCard load={load} key={`${load.demand_number}-${load.start_date}-${load.mode}`} />
              ))}
            </div>
          ) : (
            <div className="pending-empty">Aucune demande potentielle pour cette semaine.</div>
          )}
        </aside>
      </div>

      {editingShift && snapshot && (
        <ShiftEditor
          shift={editingShift}
          resources={snapshot.resources}
          onClose={() => setEditingShift(null)}
          onSaved={() => {
            setEditingShift(null);
            setRefreshKey((value) => value + 1);
          }}
        />
      )}
    </section>
  );
}
