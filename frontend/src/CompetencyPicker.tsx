import { useMemo, useState } from "react";

import { CompetencyReadModel } from "./api";

function normalize(value: string | null | undefined) {
  return (value ?? "").trim().toLocaleLowerCase("fr-CA");
}

export default function CompetencyPicker({
  competencies,
  selectedIds,
  onChange,
  disabled = false,
  multiple = true,
  label = "Compétences",
  placeholder = "Rechercher une compétence…",
}: {
  competencies: CompetencyReadModel[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  multiple?: boolean;
  label?: string;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const selected = useMemo(
    () => competencies.filter((row) => selectedIds.includes(row.id)),
    [competencies, selectedIds],
  );
  const visible = useMemo(() => {
    const wanted = normalize(query);
    return competencies.filter((row) => {
      if (!row.active && !selectedIds.includes(row.id)) return false;
      if (!wanted) return true;
      return normalize(`${row.name} ${row.description ?? ""}`).includes(wanted);
    });
  }, [competencies, selectedIds, query]);

  return (
    <div className="competency-picker">
      <span className="competency-picker-label">{label}</span>
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        disabled={disabled}
        placeholder={placeholder}
        aria-label={`Recherche — ${label}`}
      />
      <select
        multiple={multiple}
        size={multiple ? Math.min(Math.max(visible.length, 3), 7) : undefined}
        value={multiple ? selectedIds : selectedIds[0] ?? ""}
        onChange={(event) => {
          if (multiple) {
            onChange(Array.from(event.currentTarget.selectedOptions).map((option) => option.value));
          } else {
            onChange(event.currentTarget.value ? [event.currentTarget.value] : []);
          }
        }}
        disabled={disabled}
        aria-label={label}
      >
        {!multiple && <option value="">Aucune compétence</option>}
        {visible.map((row) => (
          <option value={row.id} key={row.id}>
            {row.name}{row.active ? "" : " — inactive"}
          </option>
        ))}
      </select>
      {selected.length > 0 ? (
        <div className="competency-chips">
          {selected.map((row) => (
            <button
              type="button"
              className="competency-chip"
              key={row.id}
              disabled={disabled}
              onClick={() => onChange(selectedIds.filter((id) => id !== row.id))}
              title="Retirer cette compétence"
            >
              {row.name} ×
            </button>
          ))}
        </div>
      ) : (
        <small>Aucune compétence sélectionnée.</small>
      )}
    </div>
  );
}
