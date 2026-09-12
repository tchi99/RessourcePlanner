import { CSSProperties, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  DemandReadModel,
  PendingDemandLoadReadModel,
  PlanningSnapshotReadModel,
  ProjectReadModel,
  WorkPackageReadModel,
  getPlanningSnapshot,
  getProjects,
  getWorkPackages,
} from "./api";
import {
  addDays,
  dayDistance,
  formatWeekRange,
  parseIsoDate,
  startOfWeek,
  toIsoDate,
} from "./dates";
import MediumTermCapacityPanel from "./MediumTermCapacityPanel";
import WorkPackageEditor from "./WorkPackageEditor";

const HORIZONS = [4, 8, 12] as const;

type HorizonWeeks = (typeof HORIZONS)[number];

type ProjectRow = {
  project: ProjectReadModel;
  workPackages: Array<{
    workPackage: WorkPackageReadModel;
    demands: DemandReadModel[];
    pendingLoads: PendingDemandLoadReadModel[];
  }>;
};

function normalize(value: string | null | undefined) {
  return (value ?? "").trim().toLocaleLowerCase("fr-CA");
}

function hours(value: number | null | undefined) {
  if (value == null) return "—";
  return `${new Intl.NumberFormat("fr-CA", { maximumFractionDigits: 1 }).format(value)} h`;
}

function isoWeekNumber(value: Date) {
  const date = new Date(Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()));
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

function overlapsWindow(workPackage: WorkPackageReadModel, start: Date, end: Date) {
  if (!workPackage.start_date && !workPackage.end_date) return true;
  const packageStart = workPackage.start_date ? parseIsoDate(workPackage.start_date) : start;
  const packageEnd = workPackage.end_date ? parseIsoDate(workPackage.end_date) : packageStart;
  return packageEnd >= start && packageStart <= end;
}

function packageSearchText(
  project: ProjectReadModel,
  workPackage: WorkPackageReadModel,
  demands: DemandReadModel[],
) {
  return normalize([
    project.number,
    project.name,
    project.client,
    project.project_manager,
    workPackage.reference,
    workPackage.code,
    workPackage.name,
    workPackage.description,
    workPackage.status,
    ...demands.flatMap((demand) => [demand.number, demand.description, demand.requester]),
  ].filter(Boolean).join(" "));
}

function placement(workPackage: WorkPackageReadModel, horizonStart: Date, horizonWeeks: number) {
  if (!workPackage.start_date && !workPackage.end_date) return null;
  const horizonEnd = addDays(horizonStart, horizonWeeks * 7 - 1);
  const rawStart = workPackage.start_date ? parseIsoDate(workPackage.start_date) : horizonStart;
  const rawEnd = workPackage.end_date ? parseIsoDate(workPackage.end_date) : rawStart;
  if (rawEnd < horizonStart || rawStart > horizonEnd) return null;

  const clampedStart = rawStart < horizonStart ? horizonStart : rawStart;
  const clampedEnd = rawEnd > horizonEnd ? horizonEnd : rawEnd;
  const firstWeek = Math.max(0, Math.floor(dayDistance(horizonStart, clampedStart) / 7));
  const lastWeek = Math.min(
    horizonWeeks - 1,
    Math.floor(dayDistance(horizonStart, clampedEnd) / 7),
  );
  return { column: firstWeek + 2, span: Math.max(1, lastWeek - firstWeek + 1) };
}

function isTentative(demand: DemandReadModel) {
  return normalize(demand.confirmation).includes("tentative");
}

function demandTone(demand: DemandReadModel, pending: boolean, hasApprovedPlan: boolean) {
  if (pending) return "pending";
  if (hasApprovedPlan && isTentative(demand)) return "tentative";
  if (hasApprovedPlan) return "planned";
  const status = normalize(demand.status);
  if (status.includes("correction")) return "correction";
  if (status.includes("brouillon")) return "draft";
  return "neutral";
}

function demandDetails(demand: DemandReadModel, label: string) {
  const window = `${demand.desired_start || "Date à préciser"} → ${demand.desired_end || demand.desired_start || "Date à préciser"}`;
  const estimate = demand.estimated_hours == null ? "Heures à préciser" : hours(demand.estimated_hours);
  const resources = `${demand.resource_count} ressource${demand.resource_count > 1 ? "s" : ""}`;
  const competencies = demand.required_competencies || "Compétence à préciser";
  return [
    demand.project_number || "Projet non précisé",
    demand.number,
    label,
    window,
    estimate,
    resources,
    competencies,
  ].join(" · ");
}

function WorkPackageRow({
  project,
  workPackage,
  demands,
  pendingLoads,
  snapshot,
  horizonStart,
  horizonWeeks,
  onOpenDemands,
  onEdit,
}: {
  project: ProjectReadModel;
  workPackage: WorkPackageReadModel;
  demands: DemandReadModel[];
  pendingLoads: PendingDemandLoadReadModel[];
  snapshot: PlanningSnapshotReadModel;
  horizonStart: Date;
  horizonWeeks: number;
  onOpenDemands: () => void;
  onEdit: (workPackage: WorkPackageReadModel) => void;
}) {
  const grid = placement(workPackage, horizonStart, horizonWeeks);
  const template = `250px repeat(${horizonWeeks}, minmax(96px, 1fr))`;
  const pendingByDemand = new Map(pendingLoads.map((load) => [load.demand_number, load]));
  const plannedNumbers = new Set(
    snapshot.segments
      .map((segment) => segment.demand_number)
      .filter((number): number is string => Boolean(number)),
  );

  return (
    <div className="mt-timeline-row" style={{ gridTemplateColumns: template }}>
      <div className="mt-package-identity">
        <div className="mt-package-title">
          <strong>{workPackage.code || workPackage.reference}</strong>
          <span className="mt-status-pill">{workPackage.status}</span>
        </div>
        <span>{workPackage.name}</span>
        <small>
          {workPackage.start_date || "Date à préciser"}
          {workPackage.end_date ? ` → ${workPackage.end_date}` : ""}
          {workPackage.planned_hours != null ? ` · ${hours(workPackage.planned_hours)}` : ""}
        </small>
        <button className="mt-edit-package" type="button" onClick={() => onEdit(workPackage)}>
          Modifier
        </button>
      </div>

      {Array.from({ length: horizonWeeks }, (_, index) => (
        <div className="mt-week-cell" style={{ gridColumn: index + 2 }} key={index} />
      ))}

      <article
        className={`mt-package-bar ${grid ? "" : "is-unscheduled"}`}
        style={grid
          ? { gridColumn: `${grid.column} / span ${grid.span}` }
          : { gridColumn: `2 / span ${horizonWeeks}` }}
        title={`${project.number} — ${workPackage.name}`}
      >
        <div className="mt-package-bar-heading">
          <strong>{workPackage.name}</strong>
          <span>{hours(workPackage.planned_hours)}</span>
        </div>
        {workPackage.description && <small>{workPackage.description}</small>}
        <div className="mt-demand-chips">
          {demands.length === 0 ? (
            <span className="mt-demand-empty">Aucune demande dans l’horizon</span>
          ) : demands.map((demand) => {
            const pendingLoad = pendingByDemand.get(demand.number);
            const planned = plannedNumbers.has(demand.number);
            const replacement = normalize(pendingLoad?.mode) === "replacement";
            const tentative = isTentative(demand);
            const tone = demandTone(demand, Boolean(pendingLoad), planned);
            const label = pendingLoad
              ? replacement ? "Soumise · modification en attente" : "Soumise · charge potentielle"
              : planned
                ? tentative ? "Plan approuvé · tentative" : "Plan approuvé · confirmée"
                : demand.status;
            return (
              <button
                type="button"
                className={`mt-demand-chip ${tone}`}
                key={demand.number}
                onClick={onOpenDemands}
                title={demandDetails(demand, label)}
                aria-label={demandDetails(demand, label)}
              >
                <strong>{demand.number}</strong>
                <span>{label}</span>
                <small>
                  {hours(demand.estimated_hours)} · {demand.resource_count} res. · {demand.required_competencies || "Comp. à préciser"}
                </small>
              </button>
            );
          })}
        </div>
      </article>
    </div>
  );
}

export default function MediumTermPage({ onOpenDemands }: { onOpenDemands: () => void }) {
  const [horizonStart, setHorizonStart] = useState(() => startOfWeek(new Date()));
  const [horizonWeeks, setHorizonWeeks] = useState<HorizonWeeks>(8);
  const [projects, setProjects] = useState<ProjectReadModel[]>([]);
  const [workPackages, setWorkPackages] = useState<WorkPackageReadModel[]>([]);
  const [snapshot, setSnapshot] = useState<PlanningSnapshotReadModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");
  const [managerFilter, setManagerFilter] = useState("all");
  const [editor, setEditor] = useState<WorkPackageReadModel | null | undefined>(undefined);
  const [refreshKey, setRefreshKey] = useState(0);

  const horizonEnd = useMemo(
    () => addDays(horizonStart, horizonWeeks * 7 - 1),
    [horizonStart, horizonWeeks],
  );
  const start = toIsoDate(horizonStart);
  const end = toIsoDate(horizonEnd);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      getProjects(true, controller.signal),
      getWorkPackages("", true, controller.signal),
      getPlanningSnapshot(start, end, controller.signal),
    ])
      .then(([projectRows, packageRows, planning]) => {
        setProjects(projectRows);
        setWorkPackages(packageRows);
        setSnapshot(planning);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        if (reason instanceof ApiError) {
          setError(`${reason.message}${reason.code ? ` (${reason.code})` : ""}`);
          return;
        }
        setError(reason instanceof Error ? reason.message : "Impossible de charger le moyen terme.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [start, end, refreshKey]);

  const weeks = useMemo(
    () => Array.from({ length: horizonWeeks }, (_, index) => addDays(horizonStart, index * 7)),
    [horizonStart, horizonWeeks],
  );

  const managerOptions = useMemo(() => {
    const values = new Set(projects.map((project) => project.project_manager || "Non assigné"));
    return [...values].sort((left, right) => left.localeCompare(right, "fr-CA"));
  }, [projects]);

  const projectOptions = useMemo(
    () => [...projects].sort((left, right) => left.number.localeCompare(right.number, "fr-CA")),
    [projects],
  );

  const groupedRows = useMemo(() => {
    if (!snapshot) return [] as Array<[string, ProjectRow[]]>;
    const query = normalize(search);
    const demandByPackage = new Map<string, DemandReadModel[]>();
    snapshot.demands.forEach((demand) => {
      if (!demand.work_package_ref) return;
      const rows = demandByPackage.get(demand.work_package_ref) ?? [];
      rows.push(demand);
      demandByPackage.set(demand.work_package_ref, rows);
    });
    const pendingByPackage = new Map<string, PendingDemandLoadReadModel[]>();
    snapshot.pending_loads.forEach((load) => {
      if (!load.work_package_ref) return;
      const rows = pendingByPackage.get(load.work_package_ref) ?? [];
      rows.push(load);
      pendingByPackage.set(load.work_package_ref, rows);
    });

    const groups = new Map<string, ProjectRow[]>();
    projects.forEach((project) => {
      const manager = project.project_manager || "Non assigné";
      if (managerFilter !== "all" && manager !== managerFilter) return;
      if (projectFilter !== "all" && project.number !== projectFilter) return;

      const projectMatches = !query || normalize([
        project.number,
        project.name,
        project.client,
        project.project_manager,
      ].filter(Boolean).join(" ")).includes(query);

      const packages = workPackages
        .filter((workPackage) => workPackage.project_number === project.number)
        .filter((workPackage) => overlapsWindow(workPackage, horizonStart, horizonEnd))
        .map((workPackage) => {
          const demands = demandByPackage.get(workPackage.reference) ?? [];
          const pendingLoads = pendingByPackage.get(workPackage.reference) ?? [];
          return { workPackage, demands, pendingLoads };
        })
        .filter(({ workPackage, demands }) => (
          projectMatches || !query || packageSearchText(project, workPackage, demands).includes(query)
        ));

      if (query && !projectMatches && packages.length === 0) return;

      const rows = groups.get(manager) ?? [];
      rows.push({ project, workPackages: packages });
      groups.set(manager, rows);
    });

    return [...groups.entries()]
      .sort((left, right) => left[0].localeCompare(right[0], "fr-CA"))
      .map(([manager, rows]) => [
        manager,
        rows.sort((left, right) => left.project.number.localeCompare(right.project.number, "fr-CA")),
      ] as [string, ProjectRow[]]);
  }, [
    snapshot,
    projects,
    workPackages,
    managerFilter,
    projectFilter,
    search,
    horizonStart,
    horizonEnd,
  ]);

  const visibleProjects = groupedRows.reduce((sum, [, rows]) => sum + rows.length, 0);
  const visiblePackages = groupedRows.reduce(
    (sum, [, rows]) => sum + rows.reduce((subtotal, row) => subtotal + row.workPackages.length, 0),
    0,
  );
  const visibleDemandNumbers = new Set(
    groupedRows.flatMap(([, rows]) => rows.flatMap((row) => row.workPackages.flatMap(
      (entry) => entry.demands.map((demand) => demand.number),
    ))),
  );
  const visiblePending = snapshot?.pending_loads.filter((load) => visibleDemandNumbers.has(load.demand_number)).length ?? 0;

  const headerStyle: CSSProperties = {
    gridTemplateColumns: `250px repeat(${horizonWeeks}, minmax(96px, 1fr))`,
  };

  const defaultProject = projectFilter !== "all"
    ? projectFilter
    : projectOptions[0]?.number || "";

  return (
    <section className="medium-term-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Planification moyen terme</span>
          <h1>{start} → {end}</h1>
          <p>
            WorkPackages, demandes et échéancier moyen terme. Les calculs de charge restent autoritaires côté FastAPI.
          </p>
        </div>
        <div className="page-actions">
          <button className="mt-create-package" type="button" onClick={() => setEditor(null)}>
            + WorkPackage
          </button>
          <button className="mt-demands-button" type="button" onClick={onOpenDemands}>
            Ouvrir les demandes
          </button>
          <div className="week-navigation" role="group" aria-label="Navigation moyen terme">
            <button type="button" onClick={() => setHorizonStart((value) => addDays(value, -28))}>← 4 sem.</button>
            <button type="button" onClick={() => setHorizonStart(startOfWeek(new Date()))}>Aujourd’hui</button>
            <button type="button" onClick={() => setHorizonStart((value) => addDays(value, 28))}>4 sem. →</button>
          </div>
        </div>
      </div>

      <div className="metric-grid mt-metrics">
        <article><span>Projets affichés</span><strong>{loading ? "—" : visibleProjects}</strong><small>Après filtres</small></article>
        <article><span>WorkPackages</span><strong>{loading ? "—" : visiblePackages}</strong><small>Dans l’horizon</small></article>
        <article><span>Demandes liées</span><strong>{loading ? "—" : visibleDemandNumbers.size}</strong><small>Fenêtre moyen terme</small></article>
        <article><span>Charges potentielles</span><strong>{loading ? "—" : visiblePending}</strong><small>Calculées par le backend</small></article>
      </div>

      <MediumTermCapacityPanel
        buckets={snapshot?.capacity_buckets ?? []}
        loading={loading}
      />

      <div className="filter-bar mt-filters">
        <label className="search-field">
          <span>Recherche</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Projet, lot, demande…" />
        </label>
        <label>
          <span>Chargé de projet</span>
          <select value={managerFilter} onChange={(event) => setManagerFilter(event.target.value)}>
            <option value="all">Tous</option>
            {managerOptions.map((manager) => <option value={manager} key={manager}>{manager}</option>)}
          </select>
        </label>
        <label>
          <span>Projet</span>
          <select value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}>
            <option value="all">Tous les projets</option>
            {projectOptions.map((project) => <option value={project.number} key={project.id}>{project.number} — {project.name}</option>)}
          </select>
        </label>
        <label>
          <span>Horizon</span>
          <select value={horizonWeeks} onChange={(event) => setHorizonWeeks(Number(event.target.value) as HorizonWeeks)}>
            {HORIZONS.map((weeksCount) => <option value={weeksCount} key={weeksCount}>{weeksCount} semaines</option>)}
          </select>
        </label>
      </div>

      {error && (
        <div className="error-panel">
          <strong>Le moyen terme n’a pas pu être chargé.</strong>
          <span>{error}</span>
          <small>Vérifie que FastAPI fonctionne et que la base locale est migrée.</small>
        </div>
      )}

      <div className={`mt-board ${loading ? "is-loading" : ""}`}>
        <div className="mt-board-scroll">
          <div className="mt-header" style={headerStyle}>
            <div className="mt-project-header">Projet / WorkPackage</div>
            {weeks.map((week, index) => (
              <div className="mt-week-header" key={toIsoDate(week)} style={{ gridColumn: index + 2 }}>
                <strong>S{String(isoWeekNumber(week)).padStart(2, "0")}</strong>
                <span>{formatWeekRange(week)}</span>
              </div>
            ))}
          </div>

          {!loading && groupedRows.length === 0 && !error && (
            <div className="mt-empty">Aucun projet ou WorkPackage ne correspond aux filtres dans cet horizon.</div>
          )}

          {groupedRows.map(([manager, rows]) => (
            <section className="mt-manager-group" key={manager}>
              <header><strong>{manager}</strong><span>{rows.length} projet(s)</span></header>
              {rows.map(({ project, workPackages: projectPackages }) => (
                <div className="mt-project-block" key={project.id}>
                  <div className="mt-project-strip">
                    <strong>{project.number}</strong>
                    <span>{project.name}</span>
                    <small>{project.client || "Client non précisé"}</small>
                  </div>
                  {projectPackages.length === 0 ? (
                    <div className="mt-no-package">Aucun WorkPackage actif dans l’horizon.</div>
                  ) : projectPackages.map(({ workPackage, demands, pendingLoads }) => (
                    <WorkPackageRow
                      key={workPackage.id}
                      project={project}
                      workPackage={workPackage}
                      demands={demands}
                      pendingLoads={pendingLoads}
                      snapshot={snapshot!}
                      horizonStart={horizonStart}
                      horizonWeeks={horizonWeeks}
                      onOpenDemands={onOpenDemands}
                      onEdit={setEditor}
                    />
                  ))}
                </div>
              ))}
            </section>
          ))}
        </div>
      </div>

      <div className="mt-legend">
        <span><i className="planned" /> Plan approuvé confirmé</span>
        <span><i className="tentative" /> Plan approuvé tentative</span>
        <span><i className="pending" /> Soumise / modification en attente</span>
        <span><i className="draft" /> Brouillon / autre état</span>
        <small>Capacité, exposition et résiduel proviennent du snapshot FastAPI; React ne recalcule ni la projection ni le non-double-comptage.</small>
      </div>

      {editor !== undefined && (
        <WorkPackageEditor
          projects={projects}
          workPackage={editor}
          defaultProjectNumber={editor?.project_number || defaultProject}
          onClose={() => setEditor(undefined)}
          onSaved={() => {
            setEditor(undefined);
            setRefreshKey((value) => value + 1);
          }}
        />
      )}
    </section>
  );
}