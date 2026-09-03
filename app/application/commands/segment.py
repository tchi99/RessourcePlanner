from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from ...domain.confirmation import normalize_confirmation
from ..errors import ApplicationValidationError
from .common import (
    UNSET,
    UnsetType,
    bool_value,
    date_value,
    float_value,
    optional_text,
    required_text,
    text,
    validate_date_window,
)


def _confirmation(value: object, *, allow_none: bool = False) -> str | None:
    if value in (None, "") and allow_none:
        return None
    try:
        return normalize_confirmation(value)
    except ValueError as exc:
        raise ApplicationValidationError(
            str(exc),
            code="segment_confirmation_invalid",
            context={"field": "confirmation", "value": value},
        ) from exc


@dataclass(frozen=True, slots=True)
class SegmentCreateCommand:
    demand_number: str
    start_date: date
    end_date: date
    planned_hours: float
    project_number: str | None = None
    project_name: str | None = None
    technician: str | None = None
    status: str = "À assigner"
    description: str = ""
    source_effort_row: int | str | None = None
    required_competency: str | None = None
    planning_type: str = "Flexible"
    priority: str = "Normale"
    outside_standard_hours: bool = False
    confirmation: str | None = None

    def __post_init__(self) -> None:
        required_text(
            self.demand_number,
            field="segment_demand",
            message="La demande est requise.",
        )
        validate_date_window(self.start_date, self.end_date, prefix="segment")
        if self.planned_hours <= 0:
            raise ApplicationValidationError(
                "Les heures prévues doivent être supérieures à zéro.",
                code="segment_hours_invalid",
                context={"field": "planned_hours", "value": self.planned_hours},
            )
        if self.confirmation is not None:
            _confirmation(self.confirmation)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "SegmentCreateCommand":
        start = date_value(values.get("DateDebut"), field="segment_start", required=True)
        end = date_value(values.get("DateFin"), field="segment_end", required=False) or start
        hours = float_value(
            values.get("HeuresPrevues"),
            field="segment_hours",
            required=True,
            minimum=0.01,
        )
        return cls(
            demand_number=required_text(
                values.get("NoDemande"),
                field="segment_demand",
                message="La demande est requise.",
            ),
            start_date=start,  # type: ignore[arg-type]
            end_date=end,  # type: ignore[arg-type]
            planned_hours=hours,  # type: ignore[arg-type]
            project_number=optional_text(values.get("NumeroProjet")),
            project_name=optional_text(values.get("NomProjet")),
            technician=optional_text(values.get("Technicien")),
            status=text(values.get("Statut")) or "À assigner",
            description=text(values.get("Description")),
            source_effort_row=values.get("SourceEffortRow"),
            required_competency=optional_text(values.get("CompetenceRequise")),
            planning_type=text(values.get("TypePlanification")) or "Flexible",
            priority=text(values.get("Priorite")) or "Normale",
            outside_standard_hours=bool_value(values.get("HorsHoraireAutorise")),
            confirmation=_confirmation(values.get("Confirmation"), allow_none=True),
        )

    def to_repository_values(self) -> dict[str, Any]:
        return {
            "NoDemande": text(self.demand_number),
            "NumeroProjet": self.project_number,
            "NomProjet": self.project_name,
            "Technicien": self.technician,
            "DateDebut": self.start_date,
            "DateFin": self.end_date,
            "HeuresPrevues": round(float(self.planned_hours), 2),
            "Statut": text(self.status) or "À assigner",
            "Description": text(self.description),
            "SourceEffortRow": self.source_effort_row,
            "CompetenceRequise": self.required_competency,
            "TypePlanification": text(self.planning_type) or "Flexible",
            "Priorite": text(self.priority) or "Normale",
            "HorsHoraireAutorise": "Oui" if self.outside_standard_hours else "Non",
            "Confirmation": (
                _confirmation(self.confirmation) if self.confirmation is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class SegmentUpdateCommand:
    segment_id: str
    demand_number: str | None | UnsetType = UNSET
    project_number: str | None | UnsetType = UNSET
    project_name: str | None | UnsetType = UNSET
    technician: str | None | UnsetType = UNSET
    start_date: date | None | UnsetType = UNSET
    end_date: date | None | UnsetType = UNSET
    planned_hours: float | None | UnsetType = UNSET
    status: str | None | UnsetType = UNSET
    description: str | None | UnsetType = UNSET
    source_effort_row: int | str | None | UnsetType = UNSET
    required_competency: str | None | UnsetType = UNSET
    planning_type: str | None | UnsetType = UNSET
    priority: str | None | UnsetType = UNSET
    outside_standard_hours: bool | UnsetType = UNSET
    confirmation: str | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        required_text(
            self.segment_id,
            field="segment_id",
            message="Le segment est requis.",
        )
        if isinstance(self.start_date, date) and isinstance(self.end_date, date):
            validate_date_window(self.start_date, self.end_date, prefix="segment")
        if isinstance(self.planned_hours, (int, float)) and self.planned_hours <= 0:
            raise ApplicationValidationError(
                "Les heures prévues doivent être supérieures à zéro.",
                code="segment_hours_invalid",
                context={"field": "planned_hours", "value": self.planned_hours},
            )
        if self.confirmation is not UNSET and self.confirmation is not None:
            _confirmation(self.confirmation)

    @classmethod
    def from_mapping(
        cls,
        segment_id: str,
        updates: Mapping[str, Any],
    ) -> "SegmentUpdateCommand":
        known = {
            "NoDemande",
            "NumeroProjet",
            "NomProjet",
            "Technicien",
            "DateDebut",
            "DateFin",
            "HeuresPrevues",
            "Statut",
            "Description",
            "SourceEffortRow",
            "CompetenceRequise",
            "TypePlanification",
            "Priorite",
            "HorsHoraireAutorise",
            "Confirmation",
        }
        unknown = sorted(set(updates) - known)
        if unknown:
            raise ApplicationValidationError(
                "La modification du segment contient des champs non autorisés.",
                code="segment_update_fields_invalid",
                context={"fields": unknown},
            )

        def present(key: str, converter: Any) -> Any:
            return converter(updates[key]) if key in updates else UNSET

        return cls(
            segment_id=required_text(
                segment_id,
                field="segment_id",
                message="Le segment est requis.",
            ),
            demand_number=present("NoDemande", optional_text),
            project_number=present("NumeroProjet", optional_text),
            project_name=present("NomProjet", optional_text),
            technician=present("Technicien", optional_text),
            start_date=(
                date_value(updates["DateDebut"], field="segment_start", required=False)
                if "DateDebut" in updates
                else UNSET
            ),
            end_date=(
                date_value(updates["DateFin"], field="segment_end", required=False)
                if "DateFin" in updates
                else UNSET
            ),
            planned_hours=(
                float_value(
                    updates["HeuresPrevues"],
                    field="segment_hours",
                    required=True,
                    minimum=0.01,
                )
                if "HeuresPrevues" in updates
                else UNSET
            ),
            status=present("Statut", optional_text),
            description=present("Description", optional_text),
            source_effort_row=(
                updates["SourceEffortRow"] if "SourceEffortRow" in updates else UNSET
            ),
            required_competency=present("CompetenceRequise", optional_text),
            planning_type=present("TypePlanification", optional_text),
            priority=present("Priorite", optional_text),
            outside_standard_hours=(
                bool_value(updates["HorsHoraireAutorise"])
                if "HorsHoraireAutorise" in updates
                else UNSET
            ),
            confirmation=(
                _confirmation(updates["Confirmation"], allow_none=True)
                if "Confirmation" in updates
                else UNSET
            ),
        )

    def to_repository_values(self) -> dict[str, Any]:
        values = {
            "NoDemande": self.demand_number,
            "NumeroProjet": self.project_number,
            "NomProjet": self.project_name,
            "Technicien": self.technician,
            "DateDebut": self.start_date,
            "DateFin": self.end_date,
            "HeuresPrevues": self.planned_hours,
            "Statut": self.status,
            "Description": self.description,
            "SourceEffortRow": self.source_effort_row,
            "CompetenceRequise": self.required_competency,
            "TypePlanification": self.planning_type,
            "Priorite": self.priority,
            "HorsHoraireAutorise": (
                "Oui"
                if self.outside_standard_hours is True
                else "Non"
                if self.outside_standard_hours is False
                else UNSET
            ),
            "Confirmation": (
                _confirmation(self.confirmation, allow_none=True)
                if self.confirmation is not UNSET
                else UNSET
            ),
        }
        return {key: value for key, value in values.items() if value is not UNSET}


@dataclass(frozen=True, slots=True)
class SegmentCancelCommand:
    segment_id: str
