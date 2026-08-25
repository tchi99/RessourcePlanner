from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final, Mapping

from .errors import ApplicationValidationError


class _UnsetType:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = _UnsetType()


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    value_text = _text(value)
    return value_text or None


def _required_text(value: object, *, field: str, message: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise ApplicationValidationError(
            message,
            code=f"{field}_required",
            context={"field": field},
        )
    return normalized


def _date_value(value: object, *, field: str, required: bool) -> date | None:
    if value in (None, ""):
        if required:
            raise ApplicationValidationError(
                f"Le champ {field} est requis.",
                code=f"{field}_required",
                context={"field": field},
            )
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ApplicationValidationError(
            f"La valeur de {field} n'est pas une date valide.",
            code=f"{field}_invalid",
            context={"field": field, "value": text},
        ) from exc


def _float_value(
    value: object,
    *,
    field: str,
    required: bool = False,
    minimum: float | None = None,
) -> float | None:
    if value in (None, ""):
        if required:
            raise ApplicationValidationError(
                f"Le champ {field} est requis.",
                code=f"{field}_required",
                context={"field": field},
            )
        return None
    try:
        result = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ApplicationValidationError(
            f"La valeur de {field} doit être numérique.",
            code=f"{field}_invalid",
            context={"field": field, "value": value},
        ) from exc
    if minimum is not None and result < minimum:
        raise ApplicationValidationError(
            f"La valeur de {field} doit être au moins {minimum:g}.",
            code=f"{field}_too_small",
            context={"field": field, "minimum": minimum, "value": result},
        )
    return round(result, 2)


def _int_value(
    value: object,
    *,
    field: str,
    default: int | None = None,
    minimum: int | None = None,
) -> int | None:
    if value in (None, ""):
        return default
    try:
        result = int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError) as exc:
        raise ApplicationValidationError(
            f"La valeur de {field} doit être un nombre entier.",
            code=f"{field}_invalid",
            context={"field": field, "value": value},
        ) from exc
    if minimum is not None and result < minimum:
        raise ApplicationValidationError(
            f"La valeur de {field} doit être au moins {minimum}.",
            code=f"{field}_too_small",
            context={"field": field, "minimum": minimum, "value": result},
        )
    return result


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "oui", "x"}


def _validate_date_window(start: date | None, end: date | None, *, prefix: str) -> None:
    if start is not None and end is not None and end < start:
        raise ApplicationValidationError(
            "La date de fin ne peut pas précéder la date de début.",
            code=f"{prefix}_date_window_invalid",
            context={"start": start.isoformat(), "end": end.isoformat()},
        )


@dataclass(frozen=True, slots=True)
class DemandCreateCommand:
    project_number: str
    desired_start: date
    submit: bool = False
    project_name: str = ""
    client: str = ""
    project_manager: str = ""
    request_type: str = "Projet"
    priority: str = "Normale"
    confirmation: str = "Confirmée"
    desired_end: date | None = None
    description: str = ""
    site_client: str = ""
    location: str = ""
    resource_count: int = 1
    required_competencies: str | None = None
    estimated_hours: float | None = None
    estimated_days: float | None = None
    proposed_technician: str | None = None

    def __post_init__(self) -> None:
        if not _text(self.project_number):
            raise ApplicationValidationError(
                "Le projet est requis.",
                code="demand_project_required",
                context={"field": "project_number"},
            )
        _validate_date_window(self.desired_start, self.desired_end, prefix="demand")
        if self.resource_count < 1:
            raise ApplicationValidationError(
                "Le nombre de ressources doit être au moins 1.",
                code="demand_resource_count_invalid",
                context={"field": "resource_count", "value": self.resource_count},
            )
        for field, value in (
            ("estimated_hours", self.estimated_hours),
            ("estimated_days", self.estimated_days),
        ):
            if value is not None and value < 0:
                raise ApplicationValidationError(
                    f"{field} ne peut pas être négatif.",
                    code=f"demand_{field}_invalid",
                    context={"field": field, "value": value},
                )

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
        *,
        submit: bool = False,
    ) -> "DemandCreateCommand":
        return cls(
            project_number=_required_text(
                values.get("NumeroProjet"),
                field="demand_project",
                message="Le projet est requis.",
            ),
            desired_start=_date_value(
                values.get("DateDebutSouhaitee"),
                field="demand_start",
                required=True,
            ),  # type: ignore[arg-type]
            submit=bool(submit),
            project_name=_text(values.get("NomProjet")),
            client=_text(values.get("Client")),
            project_manager=_text(values.get("ChargeProjet")),
            request_type=_text(values.get("TypeDemande")) or "Projet",
            priority=_text(values.get("Priorite")) or "Normale",
            confirmation=_text(values.get("Confirmation")) or "Confirmée",
            desired_end=_date_value(
                values.get("DateFinSouhaitee"),
                field="demand_end",
                required=False,
            ),
            description=_text(values.get("Description")),
            site_client=_text(values.get("SiteClient")),
            location=_text(values.get("Lieu")),
            resource_count=_int_value(
                values.get("NombreRessources"),
                field="demand_resource_count",
                default=1,
                minimum=1,
            ) or 1,
            required_competencies=_optional_text(values.get("CompetencesRequises")),
            estimated_hours=_float_value(
                values.get("TempsEstimeHeures"),
                field="demand_estimated_hours",
                minimum=0,
            ),
            estimated_days=_float_value(
                values.get("TempsEstimeJours"),
                field="demand_estimated_days",
                minimum=0,
            ),
            proposed_technician=_optional_text(values.get("TechnicienPropose")),
        )

    def to_repository_values(self) -> dict[str, Any]:
        return {
            "NumeroProjet": _text(self.project_number),
            "NomProjet": _text(self.project_name),
            "Client": _text(self.client),
            "ChargeProjet": _text(self.project_manager),
            "TypeDemande": _text(self.request_type) or "Projet",
            "Priorite": _text(self.priority) or "Normale",
            "Confirmation": _text(self.confirmation) or "Confirmée",
            "DateDebutSouhaitee": self.desired_start,
            "DateFinSouhaitee": self.desired_end,
            "Description": _text(self.description),
            "SiteClient": _text(self.site_client),
            "Lieu": _text(self.location),
            "NombreRessources": int(self.resource_count),
            "CompetencesRequises": self.required_competencies,
            "TempsEstimeHeures": self.estimated_hours,
            "TempsEstimeJours": self.estimated_days,
            "TechnicienPropose": self.proposed_technician,
        }


@dataclass(frozen=True, slots=True)
class DemandUpdateCommand:
    number: str
    comment: str = "Demande modifiée dans l'application"
    project_number: str | None | _UnsetType = UNSET
    project_name: str | None | _UnsetType = UNSET
    client: str | None | _UnsetType = UNSET
    project_manager: str | None | _UnsetType = UNSET
    request_type: str | None | _UnsetType = UNSET
    priority: str | None | _UnsetType = UNSET
    confirmation: str | None | _UnsetType = UNSET
    desired_start: date | None | _UnsetType = UNSET
    desired_end: date | None | _UnsetType = UNSET
    description: str | None | _UnsetType = UNSET
    site_client: str | None | _UnsetType = UNSET
    location: str | None | _UnsetType = UNSET
    resource_count: int | None | _UnsetType = UNSET
    required_competencies: str | None | _UnsetType = UNSET
    estimated_hours: float | None | _UnsetType = UNSET
    estimated_days: float | None | _UnsetType = UNSET
    proposed_technician: str | None | _UnsetType = UNSET

    def __post_init__(self) -> None:
        if not _text(self.number):
            raise ApplicationValidationError(
                "Le numéro de demande est requis.",
                code="demand_number_required",
                context={"field": "number"},
            )
        if isinstance(self.desired_start, date) and isinstance(self.desired_end, date):
            _validate_date_window(self.desired_start, self.desired_end, prefix="demand")
        if isinstance(self.resource_count, int) and self.resource_count < 1:
            raise ApplicationValidationError(
                "Le nombre de ressources doit être au moins 1.",
                code="demand_resource_count_invalid",
                context={"field": "resource_count", "value": self.resource_count},
            )

    @classmethod
    def from_mapping(
        cls,
        number: str,
        updates: Mapping[str, Any],
        *,
        comment: str = "Demande modifiée dans l'application",
    ) -> "DemandUpdateCommand":
        known = {
            "NumeroProjet",
            "NomProjet",
            "Client",
            "ChargeProjet",
            "TypeDemande",
            "Priorite",
            "Confirmation",
            "DateDebutSouhaitee",
            "DateFinSouhaitee",
            "Description",
            "SiteClient",
            "Lieu",
            "NombreRessources",
            "CompetencesRequises",
            "TempsEstimeHeures",
            "TempsEstimeJours",
            "TechnicienPropose",
        }
        unknown = sorted(set(updates) - known)
        if unknown:
            raise ApplicationValidationError(
                "La modification contient des champs non autorisés.",
                code="demand_update_fields_invalid",
                context={"fields": unknown},
            )

        def present(key: str, converter: Any) -> Any:
            return converter(updates[key]) if key in updates else UNSET

        return cls(
            number=_required_text(
                number,
                field="demand_number",
                message="Le numéro de demande est requis.",
            ),
            comment=str(comment or ""),
            project_number=present("NumeroProjet", _optional_text),
            project_name=present("NomProjet", _optional_text),
            client=present("Client", _optional_text),
            project_manager=present("ChargeProjet", _optional_text),
            request_type=present("TypeDemande", _optional_text),
            priority=present("Priorite", _optional_text),
            confirmation=present("Confirmation", _optional_text),
            desired_start=(
                _date_value(updates["DateDebutSouhaitee"], field="demand_start", required=False)
                if "DateDebutSouhaitee" in updates
                else UNSET
            ),
            desired_end=(
                _date_value(updates["DateFinSouhaitee"], field="demand_end", required=False)
                if "DateFinSouhaitee" in updates
                else UNSET
            ),
            description=present("Description", _optional_text),
            site_client=present("SiteClient", _optional_text),
            location=present("Lieu", _optional_text),
            resource_count=(
                _int_value(
                    updates["NombreRessources"],
                    field="demand_resource_count",
                    minimum=1,
                )
                if "NombreRessources" in updates
                else UNSET
            ),
            required_competencies=present("CompetencesRequises", _optional_text),
            estimated_hours=(
                _float_value(
                    updates["TempsEstimeHeures"],
                    field="demand_estimated_hours",
                    minimum=0,
                )
                if "TempsEstimeHeures" in updates
                else UNSET
            ),
            estimated_days=(
                _float_value(
                    updates["TempsEstimeJours"],
                    field="demand_estimated_days",
                    minimum=0,
                )
                if "TempsEstimeJours" in updates
                else UNSET
            ),
            proposed_technician=present("TechnicienPropose", _optional_text),
        )

    def to_repository_values(self) -> dict[str, Any]:
        mapping = {
            "NumeroProjet": self.project_number,
            "NomProjet": self.project_name,
            "Client": self.client,
            "ChargeProjet": self.project_manager,
            "TypeDemande": self.request_type,
            "Priorite": self.priority,
            "Confirmation": self.confirmation,
            "DateDebutSouhaitee": self.desired_start,
            "DateFinSouhaitee": self.desired_end,
            "Description": self.description,
            "SiteClient": self.site_client,
            "Lieu": self.location,
            "NombreRessources": self.resource_count,
            "CompetencesRequises": self.required_competencies,
            "TempsEstimeHeures": self.estimated_hours,
            "TempsEstimeJours": self.estimated_days,
            "TechnicienPropose": self.proposed_technician,
        }
        return {key: value for key, value in mapping.items() if value is not UNSET}


@dataclass(frozen=True, slots=True)
class DemandSubmitCommand:
    number: str


@dataclass(frozen=True, slots=True)
class DemandApproveCommand:
    number: str
    comment: str = ""


@dataclass(frozen=True, slots=True)
class DemandCorrectionCommand:
    number: str
    comment: str


@dataclass(frozen=True, slots=True)
class DemandCancelCommand:
    number: str


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

    def __post_init__(self) -> None:
        _required_text(
            self.demand_number,
            field="segment_demand",
            message="La demande est requise.",
        )
        _validate_date_window(self.start_date, self.end_date, prefix="segment")
        if self.planned_hours <= 0:
            raise ApplicationValidationError(
                "Les heures prévues doivent être supérieures à zéro.",
                code="segment_hours_invalid",
                context={"field": "planned_hours", "value": self.planned_hours},
            )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "SegmentCreateCommand":
        start = _date_value(values.get("DateDebut"), field="segment_start", required=True)
        end = _date_value(values.get("DateFin"), field="segment_end", required=False) or start
        hours = _float_value(
            values.get("HeuresPrevues"),
            field="segment_hours",
            required=True,
            minimum=0.01,
        )
        return cls(
            demand_number=_required_text(
                values.get("NoDemande"),
                field="segment_demand",
                message="La demande est requise.",
            ),
            start_date=start,  # type: ignore[arg-type]
            end_date=end,  # type: ignore[arg-type]
            planned_hours=hours,  # type: ignore[arg-type]
            project_number=_optional_text(values.get("NumeroProjet")),
            project_name=_optional_text(values.get("NomProjet")),
            technician=_optional_text(values.get("Technicien")),
            status=_text(values.get("Statut")) or "À assigner",
            description=_text(values.get("Description")),
            source_effort_row=values.get("SourceEffortRow"),
            required_competency=_optional_text(values.get("CompetenceRequise")),
            planning_type=_text(values.get("TypePlanification")) or "Flexible",
            priority=_text(values.get("Priorite")) or "Normale",
            outside_standard_hours=_bool_value(values.get("HorsHoraireAutorise")),
        )

    def to_repository_values(self) -> dict[str, Any]:
        return {
            "NoDemande": _text(self.demand_number),
            "NumeroProjet": self.project_number,
            "NomProjet": self.project_name,
            "Technicien": self.technician,
            "DateDebut": self.start_date,
            "DateFin": self.end_date,
            "HeuresPrevues": round(float(self.planned_hours), 2),
            "Statut": _text(self.status) or "À assigner",
            "Description": _text(self.description),
            "SourceEffortRow": self.source_effort_row,
            "CompetenceRequise": self.required_competency,
            "TypePlanification": _text(self.planning_type) or "Flexible",
            "Priorite": _text(self.priority) or "Normale",
            "HorsHoraireAutorise": "Oui" if self.outside_standard_hours else "Non",
        }


@dataclass(frozen=True, slots=True)
class SegmentUpdateCommand:
    segment_id: str
    demand_number: str | None | _UnsetType = UNSET
    project_number: str | None | _UnsetType = UNSET
    project_name: str | None | _UnsetType = UNSET
    technician: str | None | _UnsetType = UNSET
    start_date: date | None | _UnsetType = UNSET
    end_date: date | None | _UnsetType = UNSET
    planned_hours: float | None | _UnsetType = UNSET
    status: str | None | _UnsetType = UNSET
    description: str | None | _UnsetType = UNSET
    source_effort_row: int | str | None | _UnsetType = UNSET
    required_competency: str | None | _UnsetType = UNSET
    planning_type: str | None | _UnsetType = UNSET
    priority: str | None | _UnsetType = UNSET
    outside_standard_hours: bool | _UnsetType = UNSET

    def __post_init__(self) -> None:
        _required_text(
            self.segment_id,
            field="segment_id",
            message="Le segment est requis.",
        )
        if isinstance(self.start_date, date) and isinstance(self.end_date, date):
            _validate_date_window(self.start_date, self.end_date, prefix="segment")
        if isinstance(self.planned_hours, (int, float)) and self.planned_hours <= 0:
            raise ApplicationValidationError(
                "Les heures prévues doivent être supérieures à zéro.",
                code="segment_hours_invalid",
                context={"field": "planned_hours", "value": self.planned_hours},
            )

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
            segment_id=_required_text(
                segment_id,
                field="segment_id",
                message="Le segment est requis.",
            ),
            demand_number=present("NoDemande", _optional_text),
            project_number=present("NumeroProjet", _optional_text),
            project_name=present("NomProjet", _optional_text),
            technician=present("Technicien", _optional_text),
            start_date=(
                _date_value(updates["DateDebut"], field="segment_start", required=False)
                if "DateDebut" in updates
                else UNSET
            ),
            end_date=(
                _date_value(updates["DateFin"], field="segment_end", required=False)
                if "DateFin" in updates
                else UNSET
            ),
            planned_hours=(
                _float_value(
                    updates["HeuresPrevues"],
                    field="segment_hours",
                    required=True,
                    minimum=0.01,
                )
                if "HeuresPrevues" in updates
                else UNSET
            ),
            status=present("Statut", _optional_text),
            description=present("Description", _optional_text),
            source_effort_row=(
                updates["SourceEffortRow"] if "SourceEffortRow" in updates else UNSET
            ),
            required_competency=present("CompetenceRequise", _optional_text),
            planning_type=present("TypePlanification", _optional_text),
            priority=present("Priorite", _optional_text),
            outside_standard_hours=(
                _bool_value(updates["HorsHoraireAutorise"])
                if "HorsHoraireAutorise" in updates
                else UNSET
            ),
        )

    def to_repository_values(self) -> dict[str, Any]:
        mapping = {
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
                "Oui" if self.outside_standard_hours is True else "Non"
                if self.outside_standard_hours is False
                else UNSET
            ),
        }
        return {key: value for key, value in mapping.items() if value is not UNSET}


@dataclass(frozen=True, slots=True)
class SegmentCancelCommand:
    segment_id: str


@dataclass(frozen=True, slots=True)
class ManualAllocationCreateCommand:
    segment_id: str
    technician: str
    day: date
    hours: float
    outside_standard_hours: bool = False
    note: str = ""

    @classmethod
    def from_values(
        cls,
        segment_id: object,
        technician: object,
        day_value: object,
        hours_value: object,
        outside_standard_hours: bool = False,
        note: str = "",
    ) -> "ManualAllocationCreateCommand":
        return cls(
            segment_id=_required_text(
                segment_id,
                field="allocation_segment",
                message="Un segment est requis pour le quart manuel.",
            ),
            technician=_required_text(
                technician,
                field="allocation_resource",
                message="Un technicien est requis pour le quart manuel.",
            ),
            day=_date_value(day_value, field="allocation_day", required=True),  # type: ignore[arg-type]
            hours=_float_value(
                hours_value,
                field="allocation_hours",
                required=True,
                minimum=0.01,
            ),  # type: ignore[arg-type]
            outside_standard_hours=bool(outside_standard_hours),
            note=str(note or ""),
        )


@dataclass(frozen=True, slots=True)
class ManualAllocationUpdateCommand:
    allocation_id: str
    technician: str
    day: date
    hours: float
    outside_standard_hours: bool = False
    note: str = ""

    @classmethod
    def from_values(
        cls,
        allocation_id: object,
        technician: object,
        day_value: object,
        hours_value: object,
        outside_standard_hours: bool = False,
        note: str = "",
    ) -> "ManualAllocationUpdateCommand":
        created = ManualAllocationCreateCommand.from_values(
            "placeholder",
            technician,
            day_value,
            hours_value,
            outside_standard_hours,
            note,
        )
        return cls(
            allocation_id=_required_text(
                allocation_id,
                field="allocation_id",
                message="Un identifiant d'allocation est requis.",
            ),
            technician=created.technician,
            day=created.day,
            hours=created.hours,
            outside_standard_hours=created.outside_standard_hours,
            note=created.note,
        )


@dataclass(frozen=True, slots=True)
class ManualAllocationReleaseCommand:
    allocation_id: str


@dataclass(frozen=True, slots=True)
class ManualAllocationDeleteCommand:
    allocation_id: str


@dataclass(frozen=True, slots=True)
class SegmentAssignCommand:
    segment_id: str
    technician: str


@dataclass(frozen=True, slots=True)
class QuickShiftCreateCommand:
    project_number: str
    technician: str
    day: date
    hours: float
    project_name: str = ""
    outside_standard_hours: bool = False
    note: str = ""
    description: str = ""

    @classmethod
    def from_values(
        cls,
        *,
        project_number: object,
        technician: object,
        day_value: object,
        hours_value: object,
        project_name: object = "",
        outside_standard_hours: bool = False,
        note: str = "",
        description: str = "",
    ) -> "QuickShiftCreateCommand":
        return cls(
            project_number=_required_text(
                project_number,
                field="quick_shift_project",
                message="Un projet est requis pour le quart rapide.",
            ),
            technician=_required_text(
                technician,
                field="quick_shift_resource",
                message="Une ressource est requise pour le quart rapide.",
            ),
            day=_date_value(day_value, field="quick_shift_day", required=True),  # type: ignore[arg-type]
            hours=_float_value(
                hours_value,
                field="quick_shift_hours",
                required=True,
                minimum=0.01,
            ),  # type: ignore[arg-type]
            project_name=_text(project_name),
            outside_standard_hours=bool(outside_standard_hours),
            note=str(note or "").strip(),
            description=str(description or "").strip(),
        )


@dataclass(frozen=True, slots=True)
class PlanningRebuildCommand:
    """Explicit marker command for a full authoritative planning rebuild."""
