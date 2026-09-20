import type {
  BusinessContactReadModel,
  ContactResolutionReadModel,
} from "./api";

export function contactLabel(
  contacts: BusinessContactReadModel[],
  contactId: string | null | undefined,
) {
  if (!contactId) return "Hérité / non défini";
  const contact = contacts.find((row) => row.id === contactId);
  if (!contact) return `Référence inconnue · ${contactId}`;
  return `${contact.display_name}${contact.active ? "" : " · inactif"}`;
}

export function ContactSelect({
  contacts,
  value,
  onChange,
  disabled = false,
  inheritLabel = "Hériter",
}: {
  contacts: BusinessContactReadModel[];
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
  inheritLabel?: string;
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value || null)}
      disabled={disabled}
    >
      <option value="">{inheritLabel}</option>
      {contacts.map((contact) => (
        <option key={contact.id} value={contact.id}>
          {contact.display_name}{contact.active ? "" : " · inactif"}
        </option>
      ))}
    </select>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  REQUEST_OVERRIDE: "Override de la demande",
  TASK_RESPONSIBLE: "Responsable de la tâche",
  PROJECT_MANAGER: "Chargé de projet",
  RESOURCE_COORDINATOR: "Coordonnateur de la ressource",
  TASK_COORDINATOR: "Coordonnateur de la tâche",
  NONE: "Aucune source",
};

export function ResolutionSummary({
  title,
  resolution,
}: {
  title: string;
  resolution: ContactResolutionReadModel;
}) {
  const resolved = resolution.status === "RESOLVED";
  return (
    <div className={`contact-resolution ${resolved ? "is-resolved" : "is-warning"}`}>
      <span>{title}</span>
      <strong>{resolution.display_name || "Non résolu"}</strong>
      <small>
        Source : {SOURCE_LABELS[resolution.source_type] || resolution.source_type}
        {resolution.source_label ? ` · ${resolution.source_label}` : ""}
      </small>
      {(resolution.phone || resolution.email) && (
        <small>{[resolution.phone, resolution.email].filter(Boolean).join(" · ")}</small>
      )}
      {resolution.diagnostics.length > 0 && (
        <small className="contact-diagnostics">
          {resolution.diagnostics.join(" · ")}
        </small>
      )}
    </div>
  );
}
