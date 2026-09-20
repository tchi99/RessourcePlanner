import { useMemo } from "react";

import {
  CompetencyReadModel,
  DemandLineReadModel,
  DemandLineWrite,
  ResourceReadModel,
  TaskCatalogItemReadModel,
  WorkPackageReadModel,
} from "./api";
import CompetencyPicker from "./CompetencyPicker";

export type DemandLineDraft = {
  key: string;
  id?: string;
  required_resource_class: string;
  required_competency_ids: string[];
  desired_start: string;
  desired_end: string;
  desired_active_days: string;
  estimated_hours: string;
  work_package_ref: string;
  task_code: string;
  proposed_resource_id: string;
  confirmation: "Tentative" | "Confirmée";
  description: string;
  estimated_hours_source?: string | null;
};

export type DemandLineDefaults = Omit<DemandLineDraft, "key" | "id" | "estimated_hours_source">;

function draftKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `request-line-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function optionalNumber(value: string) {
  const normalized = value.trim();
  if (!normalized) return null;
  const parsed = Number(normalized.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

export function newDemandLine(defaults: DemandLineDefaults): DemandLineDraft {
  return { key: draftKey(), ...defaults };
}

export function demandLineDraftFromReadModel(line: DemandLineReadModel): DemandLineDraft {
  return {
    key: line.line_id || draftKey(),
    id: line.line_id || undefined,
    required_resource_class: line.required_resource_class ?? "",
    required_competency_ids: line.required_competency_ids ?? [],
    desired_start: line.desired_start ?? "",
    desired_end: line.desired_end ?? "",
    desired_active_days: line.desired_active_days == null ? "" : String(line.desired_active_days),
    estimated_hours: line.estimated_hours_source === "DEFAULT_8H"
      ? ""
      : line.estimated_hours == null ? "" : String(line.estimated_hours),
    work_package_ref: line.work_package_ref ?? "",
    task_code: line.task_code ?? "",
    proposed_resource_id: line.proposed_resource_id ?? "",
    confirmation: line.confirmation === "Tentative" ? "Tentative" : "Confirmée",
    description: line.description ?? "",
    estimated_hours_source: line.estimated_hours_source,
  };
}

export function demandLineWrite(line: DemandLineDraft, position: number): DemandLineWrite {
  const activeDays = optionalNumber(line.desired_active_days);
  const hours = optionalNumber(line.estimated_hours);
  return {
    ...(line.id ? { id: line.id } : {}),
    position,
    kind: "WORKFORCE",
    required_resource_class: line.required_resource_class.trim() || null,
    required_competency_ids: line.required_competency_ids,
    desired_start: line.desired_start || null,
    desired_end: line.desired_end || null,
    desired_active_days: activeDays == null || Number.isNaN(activeDays) ? null : activeDays,
    estimated_hours: hours == null || Number.isNaN(hours) ? null : hours,
    work_package_ref: line.work_package_ref || null,
    task_code: line.task_code || null,
    proposed_resource_id: line.proposed_resource_id || null,
    confirmation: line.confirmation,
    description: line.description.trim() || null,
  };
}

export function lineValidationMessage(line: DemandLineDraft, position: number): string | null {
  const number = position + 1;
  if (!line.desired_start) return `Ligne ${number} : la date de début est requise.`;
  if (line.desired_end && line.desired_end < line.desired_start) {
    return `Ligne ${number} : la date de fin ne peut pas précéder la date de début.`;
  }
  const days = optionalNumber(line.desired_active_days);
  const hours = optionalNumber(line.estimated_hours);
  if (Number.isNaN(days) || Number.isNaN(hours)) {
    return `Ligne ${number} : les jours et les heures doivent être numériques.`;
  }
  if (days != null && (!Number.isInteger(days) || days < 1)) {
    return `Ligne ${number} : les jours actifs doivent être un entier supérieur ou égal à 1.`;
  }
  if (hours != null && hours <= 0) {
    return `Ligne ${number} : les heures doivent être supérieures à zéro.`;
  }
  if (days == null && hours == null) {
    return `Ligne ${number} : indique les heures ou le nombre de jours actifs.`;
  }
  if (days != null) {
    const end = line.desired_end || line.desired_start;
    const available = Math.floor((Date.parse(end) - Date.parse(line.desired_start)) / 86_400_000) + 1;
    if (days > available) {
      return `Ligne ${number} : la cible de ${days} jours actifs dépasse les ${available} dates de la fenêtre.`;
    }
  }
  return null;
}

function lineProjectedHours(line: DemandLineDraft): number {
  const hours = optionalNumber(line.estimated_hours);
  if (hours != null && !Number.isNaN(hours)) return hours;
  const days = optionalNumber(line.desired_active_days);
  if (days != null && !Number.isNaN(days)) return days * 8;
  return 0;
}

function lineProjectedDays(line: DemandLineDraft): number {
  const days = optionalNumber(line.desired_active_days);
  return days != null && !Number.isNaN(days) ? days : 0;
}

export default function DemandLinesEditor({
  lines,
  onChange,
  defaults,
  generationCount,
  onGenerationCountChange,
  competencies,
  resources,
  workPackages,
  tasks,
  disabled = false,
}: {
  lines: DemandLineDraft[];
  onChange: (lines: DemandLineDraft[]) => void;
  defaults: DemandLineDefaults;
  generationCount: string;
  onGenerationCountChange: (value: string) => void;
  competencies: CompetencyReadModel[];
  resources: ResourceReadModel[];
  workPackages: WorkPackageReadModel[];
  tasks: TaskCatalogItemReadModel[];
  disabled?: boolean;
}) {
  const resourceClasses = useMemo(
    () => [...new Set(resources.map((row) => row.resource_class?.trim()).filter((value): value is string => Boolean(value)))].sort((a, b) => a.localeCompare(b, "fr-CA")),
    [resources],
  );
  const totalHours = useMemo(
    () => lines.reduce((sum, line) => sum + lineProjectedHours(line), 0),
    [lines],
  );
  const totalDays = useMemo(
    () => lines.reduce((sum, line) => sum + lineProjectedDays(line), 0),
    [lines],
  );

  function updateLine(index: number, patch: Partial<DemandLineDraft>) {
    onChange(lines.map((line, lineIndex) => (
      lineIndex === index ? { ...line, ...patch } : line
    )));
  }

  function addLine() {
    onChange([...lines, newDemandLine(defaults)]);
  }

  function duplicateLine(index: number) {
    const source = lines[index];
    onChange([
      ...lines.slice(0, index + 1),
      { ...source, key: draftKey(), id: undefined, estimated_hours_source: undefined },
      ...lines.slice(index + 1),
    ]);
  }

  function removeLine(index: number) {
    if (lines.length <= 1) return;
    onChange(lines.filter((_line, lineIndex) => lineIndex !== index));
  }

  function generateLines() {
    const count = Number(generationCount);
    if (!Number.isInteger(count) || count < 1) return;
    const template = lines[0] ?? newDemandLine(defaults);
    onChange(Array.from({ length: count }, (_unused, index) => ({
      ...template,
      key: draftKey(),
      id: undefined,
      estimated_hours_source: undefined,
      description: index === 0 ? template.description : template.description,
    })));
  }

  return (
    <section className="request-lines-editor" aria-label="Lignes de main-d’œuvre">
      <div className="request-lines-heading">
        <div>
          <span className="eyebrow">Besoins planifiables</span>
          <h3>Lignes de main-d’œuvre</h3>
          <p>Chaque ligne représente un slot de ressource indépendant. Les heures laissées vides sont matérialisées par le backend à 8 h par jour actif.</p>
        </div>
        <div className="request-lines-actions">
          <label>
            <span>Quantité</span>
            <input
              type="number"
              min="1"
              step="1"
              value={generationCount}
              onChange={(event) => onGenerationCountChange(event.target.value)}
              disabled={disabled}
              aria-label="Quantité de lignes à générer"
            />
          </label>
          <button type="button" className="secondary-button" onClick={generateLines} disabled={disabled}>
            Générer les lignes
          </button>
          <button type="button" className="secondary-button" onClick={addLine} disabled={disabled}>
            + Ajouter une ligne
          </button>
        </div>
      </div>

      <div className="request-lines-summary" aria-label="Récapitulatif des lignes">
        <div><strong>{lines.length}</strong><span>ligne(s)</span></div>
        <div><strong>{totalDays}</strong><span>jour(s) actif(s)</span></div>
        <div><strong>{Number(totalHours.toFixed(2))}</strong><span>heure(s) projetées</span></div>
        <small>Les heures projetées utilisent 8 h/j uniquement pour l’aperçu; le backend demeure autoritaire et persiste la valeur lors de la soumission.</small>
      </div>

      <div className="request-lines-grid">
        {lines.map((line, index) => (
          <article className="request-line-card" data-line-index={index} key={line.key}>
            <div className="request-line-title">
              <div>
                <strong>Ligne {index + 1}</strong>
                {line.id && <small>ID {line.id}</small>}
              </div>
              <div className="request-line-row-actions">
                <button type="button" className="text-button" onClick={() => duplicateLine(index)} disabled={disabled}>
                  Dupliquer
                </button>
                <button type="button" className="text-button danger" onClick={() => removeLine(index)} disabled={disabled || lines.length <= 1}>
                  Retirer
                </button>
              </div>
            </div>

            <div className="request-line-fields">
              <label>
                <span>Classe de ressource</span>
                <select
                  value={line.required_resource_class}
                  onChange={(event) => updateLine(index, { required_resource_class: event.target.value })}
                  disabled={disabled}
                >
                  <option value="">Aucune classe imposée</option>
                  {line.required_resource_class && !resourceClasses.includes(line.required_resource_class) && (
                    <option value={line.required_resource_class}>{line.required_resource_class} — historique</option>
                  )}
                  {resourceClasses.map((resourceClass) => (
                    <option value={resourceClass} key={resourceClass}>{resourceClass}</option>
                  ))}
                </select>
              </label>

              <CompetencyPicker
                competencies={competencies}
                selectedIds={line.required_competency_ids}
                onChange={(ids) => updateLine(index, { required_competency_ids: ids })}
                disabled={disabled}
                label={`Compétences requises — ligne ${index + 1}`}
                placeholder="Rechercher une compétence…"
              />

              <label>
                <span>Début</span>
                <input
                  type="date"
                  value={line.desired_start}
                  onChange={(event) => updateLine(index, { desired_start: event.target.value })}
                  disabled={disabled}
                />
              </label>

              <label>
                <span>Fin</span>
                <input
                  type="date"
                  min={line.desired_start || undefined}
                  value={line.desired_end}
                  onChange={(event) => updateLine(index, { desired_end: event.target.value })}
                  disabled={disabled}
                />
              </label>

              <label>
                <span>Jours actifs</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={line.desired_active_days}
                  onChange={(event) => updateLine(index, { desired_active_days: event.target.value })}
                  disabled={disabled}
                  placeholder="Ex. 3"
                />
              </label>

              <label>
                <span>Heures</span>
                <input
                  type="number"
                  min="0.25"
                  step="0.25"
                  value={line.estimated_hours}
                  onChange={(event) => updateLine(index, { estimated_hours: event.target.value, estimated_hours_source: event.target.value ? "EXPLICIT" : null })}
                  disabled={disabled}
                  placeholder="8 h/j si vide"
                />
                <small>
                  {line.estimated_hours
                    ? "Heures explicites."
                    : "Vide : le backend applique 8 h par jour actif à la soumission."}
                </small>
              </label>

              <label>
                <span>WorkPackage</span>
                <select
                  value={line.work_package_ref}
                  onChange={(event) => updateLine(index, { work_package_ref: event.target.value })}
                  disabled={disabled}
                >
                  <option value="">Aucun WorkPackage</option>
                  {line.work_package_ref && !workPackages.some((row) => row.reference === line.work_package_ref) && (
                    <option value={line.work_package_ref}>{line.work_package_ref} — historique</option>
                  )}
                  {workPackages.map((item) => (
                    <option value={item.reference} key={item.id}>
                      {item.code ? `${item.code} — ` : ""}{item.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Tâche ERP</span>
                <select
                  value={line.task_code}
                  onChange={(event) => updateLine(index, { task_code: event.target.value })}
                  disabled={disabled}
                >
                  <option value="">Aucune tâche</option>
                  {line.task_code && !tasks.some((row) => row.code === line.task_code) && (
                    <option value={line.task_code}>{line.task_code} — historique</option>
                  )}
                  {tasks.filter((row) => row.active || row.code === line.task_code).map((task) => (
                    <option value={task.code} key={`${task.project_number}:${task.code}`}>
                      {task.code} — {task.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Ressource proposée</span>
                <select
                  value={line.proposed_resource_id}
                  onChange={(event) => updateLine(index, { proposed_resource_id: event.target.value })}
                  disabled={disabled}
                >
                  <option value="">Aucune ressource proposée</option>
                  {line.proposed_resource_id && !resources.some((row) => row.id === line.proposed_resource_id) && (
                    <option value={line.proposed_resource_id}>{line.proposed_resource_id} — inactive/historique</option>
                  )}
                  {resources.map((resource) => (
                    <option value={resource.id} key={resource.id}>
                      {resource.name}{resource.resource_class ? ` — ${resource.resource_class}` : ""}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Confirmation</span>
                <select
                  value={line.confirmation}
                  onChange={(event) => updateLine(index, { confirmation: event.target.value === "Tentative" ? "Tentative" : "Confirmée" })}
                  disabled={disabled}
                >
                  <option value="Confirmée">Confirmée</option>
                  <option value="Tentative">Tentative</option>
                </select>
              </label>

              <label className="span-2">
                <span>Description spécifique</span>
                <textarea
                  rows={2}
                  value={line.description}
                  onChange={(event) => updateLine(index, { description: event.target.value })}
                  disabled={disabled}
                  placeholder="Optionnel — précise seulement ce qui diffère du contexte de la demande."
                />
              </label>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
