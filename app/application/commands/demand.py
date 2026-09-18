from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from ..errors import ApplicationValidationError
from .common import (
    UNSET,
    UnsetType,
    date_value,
    float_value,
    int_value,
    optional_text,
    required_text,
    text,
    validate_date_window,
)


@dataclass(frozen=True, slots=True)
class DemandCreateCommand:
    project_number: str
    desired_start: date
    submit: bool = False
    project_name: str = ""
    client: str = ""
    project_manager: str = ""
    requester: str | None = None
    work_package_ref: str | None = None
    task_code: str | None = None
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
        required_text(
            self.project_number,
            field="demand_project",
            message="Le projet est requis.",
        )
        validate_date_window(self.desired_start, self.desired_end, prefix="demand")
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
        start = date_value(
            values.get("DateDebutSouhaitee"), field="demand_start", required=True
        )
        return cls(
            project_number=required_text(
                values.get("NumeroProjet"),
                field="demand_project",
                message="Le projet est requis.",
            ),
            desired_start=start,  # type: ignore[arg-type]
            submit=bool(submit),
            project_name=text(values.get("NomProjet")),
            client=text(values.get("Client")),
            project_manager=text(values.get("ChargeProjet")),
            requester=optional_text(values.get("Demandeur")),
            work_package_ref=optional_text(values.get("SourceEffortID")),
            task_code=optional_text(values.get("TaskCode")),
            request_type=text(values.get("TypeDemande")) or "Projet",
            priority=text(values.get("Priorite")) or "Normale",
            confirmation=text(values.get("Confirmation")) or "Confirmée",
            desired_end=date_value(
                values.get("DateFinSouhaitee"), field="demand_end", required=False
            ),
            description=text(values.get("Description")),
            site_client=text(values.get("SiteClient")),
            location=text(values.get("Lieu")),
            resource_count=int_value(
                values.get("NombreRessources"),
                field="demand_resource_count",
                default=1,
                minimum=1,
            )
            or 1,
            required_competencies=optional_text(values.get("CompetencesRequises")),
            estimated_hours=float_value(
                values.get("TempsEstimeHeures"),
                field="demand_estimated_hours",
                minimum=0,
            ),
            estimated_days=float_value(
                values.get("TempsEstimeJours"),
                field="demand_estimated_days",
                minimum=0,
            ),
            proposed_technician=optional_text(values.get("TechnicienPropose")),
        )

    def to_repository_values(self) -> dict[str, Any]:
        return {
            "NumeroProjet": text(self.project_number),
            "NomProjet": text(self.project_name),
            "Client": text(self.client),
            "ChargeProjet": text(self.project_manager),
            "Demandeur": self.requester,
            "SourceEffortID": self.work_package_ref,
            "TaskCode": self.task_code,
            "TypeDemande": text(self.request_type) or "Projet",
            "Priorite": text(self.priority) or "Normale",
            "Confirmation": text(self.confirmation) or "Confirmée",
            "DateDebutSouhaitee": self.desired_start,
            "DateFinSouhaitee": self.desired_end,
            "Description": text(self.description),
            "SiteClient": text(self.site_client),
            "Lieu": text(self.location),
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
    project_number: str | None | UnsetType = UNSET
    project_name: str | None | UnsetType = UNSET
    client: str | None | UnsetType = UNSET
    project_manager: str | None | UnsetType = UNSET
    requester: str | None | UnsetType = UNSET
    work_package_ref: str | None | UnsetType = UNSET
    task_code: str | None | UnsetType = UNSET
    request_type: str | None | UnsetType = UNSET
    priority: str | None | UnsetType = UNSET
    confirmation: str | None | UnsetType = UNSET
    desired_start: date | None | UnsetType = UNSET
    desired_end: date | None | UnsetType = UNSET
    description: str | None | UnsetType = UNSET
    site_client: str | None | UnsetType = UNSET
    location: str | None | UnsetType = UNSET
    resource_count: int | None | UnsetType = UNSET
    required_competencies: str | None | UnsetType = UNSET
    estimated_hours: float | None | UnsetType = UNSET
    estimated_days: float | None | UnsetType = UNSET
    proposed_technician: str | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        required_text(
            self.number,
            field="demand_number",
            message="Le numéro de demande est requis.",
        )
        if isinstance(self.desired_start, date) and isinstance(self.desired_end, date):
            validate_date_window(self.desired_start, self.desired_end, prefix="demand")
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
            "Demandeur",
            "SourceEffortID",
            "TaskCode",
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
            number=required_text(
                number,
                field="demand_number",
                message="Le numéro de demande est requis.",
            ),
            comment=str(comment or ""),
            project_number=present("NumeroProjet", optional_text),
            project_name=present("NomProjet", optional_text),
            client=present("Client", optional_text),
            project_manager=present("ChargeProjet", optional_text),
            requester=present("Demandeur", optional_text),
            work_package_ref=present("SourceEffortID", optional_text),
            task_code=present("TaskCode", optional_text),
            request_type=present("TypeDemande", optional_text),
            priority=present("Priorite", optional_text),
            confirmation=present("Confirmation", optional_text),
            desired_start=(
                date_value(updates["DateDebutSouhaitee"], field="demand_start", required=False)
                if "DateDebutSouhaitee" in updates
                else UNSET
            ),
            desired_end=(
                date_value(updates["DateFinSouhaitee"], field="demand_end", required=False)
                if "DateFinSouhaitee" in updates
                else UNSET
            ),
            description=present("Description", optional_text),
            site_client=present("SiteClient", optional_text),
            location=present("Lieu", optional_text),
            resource_count=(
                int_value(
                    updates["NombreRessources"],
                    field="demand_resource_count",
                    minimum=1,
                )
                if "NombreRessources" in updates
                else UNSET
            ),
            required_competencies=present("CompetencesRequises", optional_text),
            estimated_hours=(
                float_value(
                    updates["TempsEstimeHeures"],
                    field="demand_estimated_hours",
                    minimum=0,
                )
                if "TempsEstimeHeures" in updates
                else UNSET
            ),
            estimated_days=(
                float_value(
                    updates["TempsEstimeJours"],
                    field="demand_estimated_days",
                    minimum=0,
                )
                if "TempsEstimeJours" in updates
                else UNSET
            ),
            proposed_technician=present("TechnicienPropose", optional_text),
        )

    def to_repository_values(self) -> dict[str, Any]:
        values = {
            "NumeroProjet": self.project_number,
            "NomProjet": self.project_name,
            "Client": self.client,
            "ChargeProjet": self.project_manager,
            "Demandeur": self.requester,
            "SourceEffortID": self.work_package_ref,
            "TaskCode": self.task_code,
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
        return {key: value for key, value in values.items() if value is not UNSET}


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
