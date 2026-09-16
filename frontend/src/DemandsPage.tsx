import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  DemandReadModel,
  DemandWrite,
  ProjectReadModel,
  ResourceReadModel,
  WorkPackageReadModel,
  createDemand,
  getDemand,
  getDemands,
  getProjects,
  getResources,
  getWorkPackages,
  updateDemand,
} from "./api";

type FormState = {
  project_number: string;
  requester: string;
  work_package_ref: string;
  priority: string;
  confirmation: "Tentative" | "Confirmée";
  desired_start: string;
  desired_end: string;
  description: string;
  resource_count: string;
  required_competencies: string;
  estimated_hours: string;
  estimated_days: string;
  proposed_technician: string;
};

type RetryReceipt = { fingerprint: string; key: string };

function todayIso() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `web-demand-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function messageFromError(reason: unknown) {
  if (reason instanceof ApiError) {
    return `${reason.message}${reason.code ? ` (${reason.code})` : ""}`;
  }
  return reason instanceof Error ? reason.message : "Impossible d'enregistrer la demande.";
}

function optionalNumber(value: string) {
  const normalized = value.trim();
  if (!normalized) return null;
  const parsed = Number(normalized.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function inclusiveCalendarDays(start: string, end: string): number {
  if (!start || !end) return 0;
  return Math.floor((Date.parse(end) - Date.parse(start)) / 86_400_000) + 1;
}

function emptyForm(projectNumber = ""): FormState {
  return {
    project_number: projectNumber,
    requester: "",
    work_package_ref: "",
    priority: "Normale",
    confirmation: "Confirmée",
    desired_start: todayIso(),
    desired_end: "",
    description: "",
    resource_count: "1",
    required_competencies: "",
    estimated_hours: "",
    estimated_days: "",
    proposed_technician: "",
  };
}

function formFromDemand(demand: DemandReadModel): FormState {
  return {
    project_number: demand.project_number ?? "",
    requester: demand.requester ?? "",
    work_package_ref: demand.work_package_ref ?? "",
    priority: demand.priority ?? "Normale",
    confirmation: (demand.confirmation === "Tentative" ? "Tentative" : "Confirmée"),
    desired_start: demand.desired_start ?? "",
    desired_end: demand.desired_end ?? "",
    description: demand.description ?? "",
    resource_count: String(demand.resource_count || 1),
    required_competencies: demand.required_competencies ?? "",
    estimated_hours: demand.estimated_hours == null ? "" : String(demand.estimated_hours),
    estimated_days: demand.estimated_days == null ? "" : String(demand.estimated_days),
    proposed_technician: demand.proposed_resource ?? "",
  };
}

function normalize(value: string | null | undefined) {
  return (value ?? "").trim().toLocaleLowerCase("fr-CA");
}

function demandSearchText(demand: DemandReadModel) {
  return normalize([
    demand.number,
    demand.status,
    demand.project_number,
    demand.project_name,
    demand.client,
    demand.project_manager,
    demand.requester,
    demand.description,
    demand.work_package_name,
    demand.required_competencies,
    demand.proposed_resource,
  ].filter(Boolean).join(" "));
}

function DemandCard({ demand, selected, onClick }: { demand: DemandReadModel; selected: boolean; onClick: () => void }) {
  const tentative = demand.confirmation === "Tentative";
  return (
    <button type="button" className={`demand-card ${selected ? "selected" : ""}`} onClick={onClick}>
      <div className="demand-card-topline">
        <strong>{demand.number}</strong>
        <span className={`demand-status status-${normalize(demand.status).replace(/[^a-z0-9]+/g, "-")}`}>{demand.status || "—"}</span>
      </div>
      <div className="demand-project">
        <strong>{demand.project_number || "Projet non défini"}</strong>
        <span>{demand.project_name || ""}</span>
      </div>
      <div className="demand-card-meta">
        <span>{demand.desired_start || "Date à définir"}{demand.desired_end && demand.desired_end !== demand.desired_start ? ` → ${demand.desired_end}` : ""}</span>
        <span>{demand.resource_count || 1} ressource(s)</span>
        <span className={tentative ? "confirmation-tentative-text" : "confirmation-confirmed-text"}>{tentative ? "Tentative" : "Confirmée"}</span>
      </div>
    </button>
  );
}

export default function DemandsPage() {
  const [demands, setDemands] = useState<DemandReadModel[]>([]);
  const [projects, setProjects] = useState<ProjectReadModel[]>([]);
  const [resources, setResources] = useState<ResourceReadModel[]>([]);
  const [workPackages, setWorkPackages] = useState<WorkPackageReadModel[]>([]);
  const [selectedNumber, setSelectedNumber] = useState<string | null>(null);
  const [selectedDemand, setSelectedDemand] = useState<DemandReadModel | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<FormState>(() => emptyForm());
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [projectFilter, setProjectFilter] = useState("all");
  const createRetry = useRef<RetryReceipt | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      getDemands(controller.signal),
      getProjects(true, controller.signal),
      getResources(true, controller.signal),
    ])
      .then(([demandRows, projectRows, resourceRows]) => {
        setDemands(demandRows);
        setProjects(projectRows);
        setResources(resourceRows);
        setSelectedNumber((current) => {
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
  }, []);

  useEffect(() => {
    if (creating || !selectedNumber) return;
    const controller = new AbortController();
    setDetailLoading(true);
    setError(null);
    getDemand(selectedNumber, controller.signal)
      .then((demand) => {
        setSelectedDemand(demand);
        setForm(formFromDemand(demand));
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(messageFromError(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });
    return () => controller.abort();
  }, [selectedNumber, creating]);

  useEffect(() => {
    const projectNumber = form.project_number;
    if (!projectNumber) {
      setWorkPackages([]);
      return;
    }
    const controller = new AbortController();
    getWorkPackages(projectNumber, false, controller.signal)
      .then(setWorkPackages)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(messageFromError(reason));
      });
    return () => controller.abort();
  }, [form.project_number]);

  const statusOptions = useMemo(
    () => [...new Set(demands.map((row) => row.status).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr-CA")),
    [demands],
  );

  const visibleDemands = useMemo(() => {
    const query = normalize(search);
    return demands.filter((demand) => {
      if (statusFilter !== "all" && demand.status !== statusFilter) return false;
      if (projectFilter !== "all" && demand.project_number !== projectFilter) return false;
      if (query && !demandSearchText(demand).includes(query)) return false;
      return true;
    });
  }, [demands, search, statusFilter, projectFilter]);

  const selectedProject = useMemo(
    () => projects.find((row) => row.number === form.project_number) ?? null,
    [projects, form.project_number],
  );

  const selectedWorkPackage = useMemo(
    () => workPackages.find((row) => row.reference === form.work_package_ref) ?? null,
    [workPackages, form.work_package_ref],
  );

  async function reloadDemand(number: string) {
    const [rows, detail] = await Promise.all([getDemands(), getDemand(number)]);
    setDemands(rows);
    setSelectedNumber(detail.number);
    setSelectedDemand(detail);
    setForm(formFromDemand(detail));
  }

  function beginCreate() {
    const firstProject = projects[0]?.number ?? "";
    setCreating(true);
    setSelectedNumber(null);
    setSelectedDemand(null);
    setForm(emptyForm(firstProject));
    setNotice(null);
    setError(null);
    createRetry.current = null;
  }

  function selectDemand(number: string) {
    if (saving) return;
    setCreating(false);
    setSelectedNumber(number);
    setNotice(null);
    setError(null);
    createRetry.current = null;
  }

  function setField<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setError(null);
    setNotice(null);

    const resourceCount = Number(form.resource_count);
    const estimatedHours = optionalNumber(form.estimated_hours);
    const estimatedDays = optionalNumber(form.estimated_days);
    if (!selectedProject) {
      setError("Sélectionne un projet actif.");
      return;
    }
    if (!form.desired_start) {
      setError("La date de début souhaitée est requise.");
      return;
    }
    if (form.desired_end && form.desired_end < form.desired_start) {
      setError("La date de fin ne peut pas précéder la date de début.");
      return;
    }
    if (!Number.isInteger(resourceCount) || resourceCount < 1) {
      setError("Le nombre de ressources doit être un entier supérieur ou égal à 1.");
      return;
    }
    if (Number.isNaN(estimatedHours) || Number.isNaN(estimatedDays)) {
      setError("Les estimations doivent être numériques.");
      return;
    }
    if (estimatedHours != null && estimatedHours <= 0) {
      setError("Les heures estimées totales doivent être supérieures à zéro lorsqu'elles sont renseignées.");
      return;
    }
    if (estimatedDays != null) {
      if (!Number.isInteger(estimatedDays) || estimatedDays < 1) {
        setError("Les jours actifs souhaités doivent être un entier supérieur ou égal à 1.");
        return;
      }
      const end = form.desired_end || form.desired_start;
      const windowDays = inclusiveCalendarDays(form.desired_start, end);
      if (estimatedDays > windowDays) {
        setError(`La cible de ${estimatedDays} jours actifs dépasse les ${windowDays} dates de la fenêtre demandée.`);
        return;
      }
    }

    const payload: DemandWrite = {
      project_number: selectedProject.number,
      project_name: selectedProject.name,
      client: selectedProject.client ?? "",
      requester: form.requester.trim() || null,
      work_package_ref: form.work_package_ref || null,
      request_type: selectedDemand?.request_type || "Projet",
      priority: form.priority,
      confirmation: form.confirmation,
      desired_start: form.desired_start,
      desired_end: form.desired_end || null,
      description: form.description.trim(),
      resource_count: resourceCount,
      required_competencies: form.required_competencies.trim() || null,
      estimated_hours: estimatedHours,
      estimated_days: estimatedDays,
      proposed_technician: form.proposed_technician || null,
    };

    setSaving(true);
    try {
      if (creating) {
        const fingerprint = JSON.stringify(payload);
        const previous = createRetry.current;
        const key = previous?.fingerprint === fingerprint ? previous.key : newIdempotencyKey();
        createRetry.current = { fingerprint, key };
        const result = await createDemand(payload, key);
        createRetry.current = null;
        setCreating(false);
        await reloadDemand(result.demand_number);
        setNotice(`Demande ${result.demand_number} créée en brouillon.`);
      } else if (selectedDemand) {
        const result = await updateDemand(
          selectedDemand.number,
          payload,
          "Demande modifiée via React V2",
        );
        await reloadDemand(result.demand_number);
        setNotice(
          result.reapproval_required
            ? "Modification enregistrée. La demande doit être approuvée de nouveau; le plan approuvé précédent reste inchangé jusque-là."
            : "Modification enregistrée.",
        );
      }
    } catch (reason: unknown) {
      setError(messageFromError(reason));
    } finally {
      setSaving(false);
    }
  }

  const missingProposedResource = form.proposed_technician
    && !resources.some((row) => row.name === form.proposed_technician)
    ? form.proposed_technician
    : null;

  return (
    <section className="demands-page">
      <div className="page-heading demands-heading">
        <div>
          <span className="eyebrow">Main-d’œuvre</span>
          <h1>Demandes</h1>
          <p>Création et modification des besoins avant leur transformation en périodes, approbation et plan opérationnel.</p>
        </div>
        <button type="button" className="primary-button demand-new-button" onClick={beginCreate} disabled={saving}>
          + Nouvelle demande
        </button>
      </div>

      {error && <div className="error-panel"><strong>Action impossible.</strong><span>{error}</span></div>}
      {notice && <div className="demand-notice" role="status">{notice}</div>}

      <div className="demand-filter-bar">
        <label>
          <span>Recherche</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Demande, projet, client, responsable…" />
        </label>
        <label>
          <span>Statut</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">Tous les statuts</option>
            {statusOptions.map((status) => <option value={status} key={status}>{status}</option>)}
          </select>
        </label>
        <label>
          <span>Projet</span>
          <select value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}>
            <option value="all">Tous les projets</option>
            {projects.map((project) => <option value={project.number} key={project.id}>{project.number} — {project.name}</option>)}
          </select>
        </label>
      </div>

      <div className="demands-workspace">
        <aside className="demand-list-panel">
          <div className="demand-list-heading">
            <strong>{loading ? "Chargement…" : `${visibleDemands.length} demande(s)`}</strong>
            <span>{demands.length} au total</span>
          </div>
          <div className="demand-list">
            {!loading && visibleDemands.length === 0 && <div className="demand-list-empty">Aucune demande ne correspond aux filtres.</div>}
            {visibleDemands.map((demand) => (
              <DemandCard
                demand={demand}
                selected={!creating && selectedNumber === demand.number}
                onClick={() => selectDemand(demand.number)}
                key={demand.number}
              />
            ))}
          </div>
        </aside>

        <div className="demand-editor-panel">
          {creating || selectedDemand ? (
            <form onSubmit={save} className="demand-editor-form">
              <div className="demand-editor-heading">
                <div>
                  <span className="eyebrow">{creating ? "Brouillon" : selectedDemand?.status}</span>
                  <h2>{creating ? "Nouvelle demande" : selectedDemand?.number}</h2>
                  {!creating && selectedDemand && (
                    <p>
                      {selectedDemand.project_number} — {selectedDemand.project_name || "Projet"}
                      {selectedDemand.work_package_name ? ` · ${selectedDemand.work_package_name}` : ""}
                    </p>
                  )}
                </div>
                {!creating && selectedDemand && (
                  <div className={`demand-confirmation-pill ${selectedDemand.confirmation === "Tentative" ? "tentative" : "confirmed"}`}>
                    {selectedDemand.confirmation || "Confirmée"}
                  </div>
                )}
              </div>

              {detailLoading && <div className="editor-loading">Actualisation du détail…</div>}

              <div className="project-master-card">
                <div>
                  <span>Responsable projet</span>
                  <strong>{selectedProject?.project_manager || selectedDemand?.project_manager || "Non défini"}</strong>
                </div>
                <div>
                  <span>Client</span>
                  <strong>{selectedProject?.client || selectedDemand?.client || "Non défini"}</strong>
                </div>
                <small>Ces données proviennent du projet et restent en lecture seule dans la demande.</small>
              </div>

              <div className="demand-form-grid">
                <label className="span-2">
                  <span>Projet</span>
                  <select
                    value={form.project_number}
                    onChange={(event) => setForm((current) => ({ ...current, project_number: event.target.value, work_package_ref: "" }))}
                    disabled={saving}
                    required
                  >
                    <option value="">Sélectionner un projet…</option>
                    {projects.map((project) => <option value={project.number} key={project.id}>{project.number} — {project.name}</option>)}
                  </select>
                </label>

                <label>
                  <span>Demandeur</span>
                  <input value={form.requester} onChange={(event) => setField("requester", event.target.value)} disabled={saving} placeholder="Nom du demandeur" />
                </label>

                <label>
                  <span>Priorité</span>
                  <select value={form.priority} onChange={(event) => setField("priority", event.target.value)} disabled={saving}>
                    <option value="Basse">Basse</option>
                    <option value="Normale">Normale</option>
                    <option value="Haute">Haute</option>
                    <option value="Urgente">Urgente</option>
                  </select>
                </label>

                <label className="span-2">
                  <span>Plage moyen terme / WorkPackage</span>
                  <select value={form.work_package_ref} onChange={(event) => setField("work_package_ref", event.target.value)} disabled={saving || !form.project_number}>
                    <option value="">Aucune plage liée</option>
                    {workPackages.map((item) => (
                      <option value={item.reference} key={item.id}>
                        {item.code ? `${item.code} — ` : ""}{item.name}{item.start_date ? ` · ${item.start_date}${item.end_date && item.end_date !== item.start_date ? ` → ${item.end_date}` : ""}` : ""}{item.status ? ` · ${item.status}` : ""}
                      </option>
                    ))}
                  </select>
                  {selectedWorkPackage && <small>{selectedWorkPackage.planned_hours == null ? "" : `${selectedWorkPackage.planned_hours} h prévues · `}{selectedWorkPackage.description || "Plage moyen terme sélectionnée"}</small>}
                </label>

                <label>
                  <span>Confirmation</span>
                  <select value={form.confirmation} onChange={(event) => setField("confirmation", event.target.value as FormState["confirmation"])} disabled={saving}>
                    <option value="Confirmée">Confirmée</option>
                    <option value="Tentative">Tentative</option>
                  </select>
                </label>

                <label>
                  <span>Ressource proposée</span>
                  <select value={form.proposed_technician} onChange={(event) => setField("proposed_technician", event.target.value)} disabled={saving}>
                    <option value="">Aucune ressource proposée</option>
                    {missingProposedResource && <option value={missingProposedResource}>{missingProposedResource} — inactive/non listée</option>}
                    {resources.map((resource) => <option value={resource.name} key={resource.id}>{resource.name}{resource.resource_class ? ` — ${resource.resource_class}` : ""}</option>)}
                  </select>
                </label>

                <label>
                  <span>Début souhaité</span>
                  <input type="date" value={form.desired_start} onChange={(event) => setField("desired_start", event.target.value)} disabled={saving} required />
                </label>

                <label>
                  <span>Fin souhaitée</span>
                  <input type="date" min={form.desired_start || undefined} value={form.desired_end} onChange={(event) => setField("desired_end", event.target.value)} disabled={saving} />
                </label>

                <label>
                  <span>Nombre de ressources simultanées</span>
                  <input type="number" min="1" step="1" value={form.resource_count} onChange={(event) => setField("resource_count", event.target.value)} disabled={saving} required />
                  <small>Décrit le parallélisme; ne multiplie jamais les heures estimées.</small>
                </label>

                <label>
                  <span>Compétences requises</span>
                  <input value={form.required_competencies} onChange={(event) => setField("required_competencies", event.target.value)} disabled={saving} placeholder="SCADA, PLC, mise en service…" />
                </label>

                <label>
                  <span>Heures estimées totales</span>
                  <input type="number" min="0.25" step="0.25" value={form.estimated_hours} onChange={(event) => setField("estimated_hours", event.target.value)} disabled={saving} placeholder="Optionnel au brouillon" />
                  <small>Volume total de main-d’œuvre pour la demande, toutes ressources confondues.</small>
                </label>

                <label>
                  <span>Jours actifs souhaités</span>
                  <input type="number" min="1" step="1" value={form.estimated_days} onChange={(event) => setField("estimated_days", event.target.value)} disabled={saving} placeholder="Optionnel" />
                  <small>Cible de répartition dans la fenêtre. Les jours ne créent pas d'heures; les heures doivent être complétées avant l'approbation.</small>
                </label>

                <label className="span-2">
                  <span>Description</span>
                  <textarea rows={5} value={form.description} onChange={(event) => setField("description", event.target.value)} disabled={saving} placeholder="Travaux demandés, contexte et contraintes…" />
                </label>
              </div>

              <div className="demand-editor-note">
                <strong>Approbation ≠ confirmation.</strong>
                <span>Une demande peut être approuvée tout en demeurant Tentative. Les heures représentent toujours le volume total; les jours actifs guident seulement sa répartition selon la capacité disponible.</span>
              </div>

              <div className="demand-editor-actions">
                {creating && (
                  <button type="button" className="secondary-button" onClick={() => {
                    setCreating(false);
                    setSelectedNumber(demands[0]?.number ?? null);
                  }} disabled={saving}>Annuler</button>
                )}
                <button type="submit" className="primary-button" disabled={saving || detailLoading}>
                  {saving ? "Enregistrement…" : creating ? "Créer le brouillon" : "Enregistrer les modifications"}
                </button>
              </div>
            </form>
          ) : (
            <div className="demand-editor-empty">
              <strong>Aucune demande sélectionnée</strong>
              <span>Sélectionne une demande ou crée un nouveau brouillon.</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
