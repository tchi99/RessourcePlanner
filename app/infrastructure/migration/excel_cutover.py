from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol


TRUE_VALUES = {"1", "true", "yes", "oui", "on", "x", "verrouille", "verrouillée"}
INACTIVE_STATUSES = {"annulé", "annule", "terminé", "termine", "fermé", "ferme"}
AD_HOC_ORIGINS = {"QUICK_SHIFT", "AD_HOC"}


class CutoverReader(Protocol):
    def records(self, sheet: str, expected_header: str) -> Sequence[Mapping[str, Any]]: ...


class RepositoryCutoverReader:
    """Read-only adapter over the current ExcelRepository without importing xlwings here."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def records(self, sheet: str, expected_header: str) -> Sequence[Mapping[str, Any]]:
        with self._repository._lock:
            rows = self._repository._sheet_as_records(sheet, expected_header)
        return tuple(dict(row) for row in rows)


@dataclass(frozen=True, slots=True)
class CutoverDiagnostic:
    severity: str
    code: str
    entity: str
    identifier: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "entity": self.entity,
            "identifier": self.identifier,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class CutoverDataset:
    projects: tuple[dict[str, Any], ...]
    work_packages: tuple[dict[str, Any], ...]
    resources: tuple[dict[str, Any], ...]
    availability: tuple[dict[str, Any], ...]
    demands: tuple[dict[str, Any], ...]
    history: tuple[dict[str, Any], ...]
    requirements: tuple[dict[str, Any], ...]
    shifts: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class CutoverExtractionReport:
    dataset: CutoverDataset
    diagnostics: tuple[CutoverDiagnostic, ...]
    counts: Mapping[str, int]
    hours: Mapping[str, float]

    @property
    def blocking_errors(self) -> tuple[CutoverDiagnostic, ...]:
        return tuple(row for row in self.diagnostics if row.severity == "error")

    @property
    def ok(self) -> bool:
        return not self.blocking_errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "counts": dict(self.counts),
            "hours": dict(self.hours),
            "blocking_error_count": len(self.blocking_errors),
            "diagnostics": [row.as_dict() for row in self.diagnostics],
        }


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    value = _text(value)
    return value or None


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _integer(value: object, default: int = 0) -> int:
    number = _number(value)
    return int(number) if number is not None else default


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).casefold() in TRUE_VALUES


def _date_value(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    text = _text(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def _datetime_value(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, (int, float)):
        return datetime(1899, 12, 30) + timedelta(days=float(value))
    text = _text(value)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _time_value(value: object) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, (int, float)):
        total_minutes = int(round((float(value) % 1.0) * 24 * 60)) % (24 * 60)
        return time(total_minutes // 60, total_minutes % 60)
    text = _text(value)
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _project_number(row: Mapping[str, Any]) -> str:
    return _text(row.get("Numéro de Projet") or row.get("N° projet") or row.get("NumeroProjet"))


def _project_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        number = _project_number(row)
        if not number:
            continue
        result.append(
            {
                "number": number,
                "name": _text(
                    row.get("Nom de référence")
                    or row.get("Description de l'appel d'offre")
                    or row.get("NomProjet")
                ),
                "client": _optional_text(row.get("Donneur d'ouvrage") or row.get("Client")),
                "project_manager": _optional_text(
                    row.get("Chargé de projet") or row.get("ChargeProjet")
                ),
                "status": _text(row.get("État") or row.get("Status")) or "active",
            }
        )
    return tuple(result)


def _work_package_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        project = _project_number(row)
        if not project and not any(value not in (None, "") for value in row.values()):
            continue
        legacy = _optional_text(row.get("IDEffort"))
        result.append(
            {
                "legacy_effort_id": legacy,
                "source_row": _integer(row.get("_row"), 0) or None,
                "project_number": project,
                "name": _text(row.get("Précision") or row.get("Compétence") or row.get("Projet"))
                or "Effort",
                "description": _optional_text(row.get("Précision")),
                "start_date": _date_value(row.get("Date de début")),
                "end_date": _date_value(row.get("Date de fin")),
                "planned_hours": _number(row.get("Efforts Prévus")),
                "status": _text(row.get("Status")) or "planned",
            }
        )
    return tuple(result)


def _resource_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        name = _text(row.get("Technicien"))
        if not name:
            continue
        result.append(
            {
                "name": name,
                "resource_class": _optional_text(row.get("Classe")),
                "competencies": _optional_text(row.get("Competences")),
                "note": _optional_text(row.get("Note")),
                "sort_order": _integer(row.get("Ordre"), 0),
                "active": True,
            }
        )
    return tuple(result)


def _availability_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        legacy = _text(row.get("ID"))
        if not legacy:
            continue
        result.append(
            {
                "legacy_id": legacy,
                "resource_name": _optional_text(row.get("Technicien")),
                "availability_type": _text(row.get("Type")),
                "start_date": _date_value(row.get("DateDebut")),
                "end_date": _date_value(row.get("DateFin")),
                "weekdays": _optional_text(row.get("JoursSemaine")),
                "start_time": _time_value(row.get("HeureDebut")),
                "end_time": _time_value(row.get("HeureFin")),
                "note": _optional_text(row.get("Note")),
                "active": str(row.get("Actif") or "Oui").strip().casefold()
                not in {"non", "no", "false", "0", "inactif"},
            }
        )
    return tuple(result)


def _demand_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        number = _text(row.get("NoDemande"))
        if not number:
            continue
        result.append(
            {
                "number": number,
                "project_number": _text(row.get("NumeroProjet")),
                "requester": _optional_text(row.get("Demandeur")),
                "request_type": _text(row.get("TypeDemande")) or "Projet",
                "priority": _text(row.get("Priorite")) or "Normale",
                "confirmation": _text(row.get("Confirmation")) or "Confirmée",
                "desired_start": _date_value(row.get("DateDebutSouhaitee")),
                "desired_end": _date_value(row.get("DateFinSouhaitee")),
                "description": _optional_text(row.get("Description")),
                "site_client": _optional_text(row.get("SiteClient")),
                "location": _optional_text(row.get("Lieu")),
                "resource_count": max(_integer(row.get("NombreRessources"), 1), 1),
                "required_competencies": _optional_text(row.get("CompetencesRequises")),
                "estimated_hours": _number(row.get("TempsEstimeHeures")),
                "estimated_days": _number(row.get("TempsEstimeJours")),
                "proposed_resource": _optional_text(row.get("TechnicienPropose")),
                "status": _text(row.get("Statut")) or "Brouillon",
                "created_at": _datetime_value(row.get("DateCreation")),
                "updated_at": _datetime_value(row.get("DateModification")),
                "approved_by": _optional_text(row.get("ApprouvePar")),
                "approved_at": _datetime_value(row.get("DateApprobation")),
                "approval_comment": _optional_text(row.get("CommentaireApprobation")),
            }
        )
    return tuple(result)


def _history_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        demand = _text(row.get("NoDemande"))
        if not demand:
            continue
        result.append(
            {
                "demand_number": demand,
                "action": _text(row.get("Action")) or "Historique",
                "old_status": _optional_text(row.get("AncienStatut")),
                "new_status": _optional_text(row.get("NouveauStatut")),
                "actor": _optional_text(row.get("Utilisateur")),
                "comment": _optional_text(row.get("Commentaire")),
                "details": _optional_text(row.get("Details")),
                "occurred_at": _datetime_value(row.get("Horodatage")),
            }
        )
    return tuple(result)


def _requirement_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        identifier = _text(row.get("IDSegment"))
        if not identifier:
            continue
        result.append(
            {
                "segment_id": identifier,
                "demand_number": _optional_text(row.get("NoDemande")),
                "project_number": _text(row.get("NumeroProjet")),
                "resource_name": _optional_text(row.get("Technicien")),
                "start_date": _date_value(row.get("DateDebut")),
                "end_date": _date_value(row.get("DateFin")) or _date_value(row.get("DateDebut")),
                "planned_hours": _number(row.get("HeuresPrevues")),
                "status": _text(row.get("Statut")) or "À assigner",
                "description": _optional_text(row.get("Description")),
                "source_effort_id": _optional_text(
                    row.get("SourceEffortID") or row.get("SourceEffortRow")
                ),
                "required_competency": _optional_text(row.get("CompetenceRequise")),
                "planning_type": _text(row.get("TypePlanification")) or "Flexible",
                "priority": _text(row.get("Priorite")) or "Normale",
                "outside_standard_hours_allowed": _truthy(row.get("HorsHoraireAutorise")),
                "origin": _text(row.get("OrigineSegment"))
                or ("REQUEST" if row.get("NoDemande") not in (None, "") else "AD_HOC"),
                "created_at": _datetime_value(row.get("DateCreation")),
                "updated_at": _datetime_value(row.get("DateModification")),
            }
        )
    return tuple(result)


def _shift_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        identifier = _text(row.get("IDAllocation"))
        if not identifier:
            continue
        locked = _truthy(row.get("Verrouillee"))
        result.append(
            {
                "allocation_id": identifier,
                "segment_id": _text(row.get("IDSegment")),
                "resource_name": _text(row.get("Technicien")),
                "work_date": _date_value(row.get("Date")),
                "hours": _number(row.get("Heures")),
                "allocation_type": _optional_text(row.get("TypeAllocation")),
                "source": "MANUAL" if locked or identifier.startswith("MAN-") else "AUTO",
                "locked": locked,
                "outside_standard_hours": _truthy(row.get("HorsHoraire")),
                "confirmation": _optional_text(row.get("Confirmation")),
                "note": _optional_text(row.get("Note")),
            }
        )
    return tuple(result)


def _duplicate_diagnostics(
    rows: Sequence[Mapping[str, Any]],
    field: str,
    *,
    entity: str,
) -> list[CutoverDiagnostic]:
    values = [_text(row.get(field)) for row in rows if _text(row.get(field))]
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    return [
        CutoverDiagnostic(
            "error",
            "duplicate_legacy_id",
            entity,
            value,
            f"Identifiant legacy dupliqué: {value}",
        )
        for value in duplicates
    ]


def _validate(dataset: CutoverDataset) -> tuple[CutoverDiagnostic, ...]:
    diagnostics: list[CutoverDiagnostic] = []
    diagnostics += _duplicate_diagnostics(dataset.projects, "number", entity="project")
    diagnostics += _duplicate_diagnostics(dataset.resources, "name", entity="resource")
    diagnostics += _duplicate_diagnostics(dataset.demands, "number", entity="demand")
    diagnostics += _duplicate_diagnostics(dataset.requirements, "segment_id", entity="requirement")
    diagnostics += _duplicate_diagnostics(dataset.shifts, "allocation_id", entity="shift")

    project_ids = {_text(row.get("number")) for row in dataset.projects}
    resource_ids = {_text(row.get("name")) for row in dataset.resources}
    demand_ids = {_text(row.get("number")) for row in dataset.demands}
    requirement_ids = {_text(row.get("segment_id")) for row in dataset.requirements}

    for row in dataset.work_packages:
        identifier = _text(row.get("legacy_effort_id")) or f"row:{row.get('source_row') or '?'}"
        if not row.get("project_number") or row.get("project_number") not in project_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_project", "work_package", identifier, "Effort lié à un projet inconnu."))
        if row.get("planned_hours") is not None and float(row["planned_hours"]) < 0:
            diagnostics.append(CutoverDiagnostic("error", "invalid_hours", "work_package", identifier, "Heures prévues négatives."))

    for row in dataset.demands:
        identifier = _text(row.get("number"))
        if row.get("project_number") not in project_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_project", "demand", identifier, "Demande liée à un projet inconnu."))
        if row.get("desired_start") is None:
            diagnostics.append(CutoverDiagnostic("error", "missing_start_date", "demand", identifier, "Date de début manquante ou invalide."))
        if row.get("desired_start") and row.get("desired_end") and row["desired_end"] < row["desired_start"]:
            diagnostics.append(CutoverDiagnostic("error", "invalid_date_window", "demand", identifier, "Fenêtre de dates invalide."))
        proposed = _text(row.get("proposed_resource"))
        if proposed and proposed not in resource_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_resource", "demand", identifier, f"Ressource proposée inconnue: {proposed}"))

    for row in dataset.history:
        identifier = _text(row.get("demand_number"))
        if identifier not in demand_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_demand", "history", identifier, "Historique lié à une demande inconnue."))
        if row.get("occurred_at") is None:
            diagnostics.append(CutoverDiagnostic("warning", "missing_timestamp", "history", identifier, "Horodatage absent ou invalide."))

    for row in dataset.availability:
        identifier = _text(row.get("legacy_id"))
        resource = _text(row.get("resource_name"))
        rule_type = _text(row.get("availability_type"))
        if resource and resource not in resource_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_resource", "availability", identifier, f"Ressource inconnue: {resource}"))
        if not resource and rule_type != "Jour férié":
            diagnostics.append(CutoverDiagnostic("error", "missing_resource", "availability", identifier, "Seul un jour férié peut être une règle globale sans ressource."))

    for row in dataset.requirements:
        identifier = _text(row.get("segment_id"))
        project = _text(row.get("project_number"))
        demand = _text(row.get("demand_number"))
        resource = _text(row.get("resource_name"))
        origin = _text(row.get("origin"))
        if project not in project_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_project", "requirement", identifier, "Segment lié à un projet inconnu."))
        if resource and resource not in resource_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_resource", "requirement", identifier, f"Ressource inconnue: {resource}"))
        if demand and demand not in demand_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_demand", "requirement", identifier, f"Demande inconnue: {demand}"))
        if origin in AD_HOC_ORIGINS and demand:
            diagnostics.append(CutoverDiagnostic("error", "adhoc_has_fake_demand", "requirement", identifier, "Un besoin ad hoc/Quick Shift ne doit pas référencer une demande."))
        if origin not in AD_HOC_ORIGINS and not demand:
            diagnostics.append(CutoverDiagnostic("error", "request_origin_without_demand", "requirement", identifier, "Un besoin REQUEST doit référencer une demande."))
        if row.get("start_date") is None or row.get("end_date") is None:
            diagnostics.append(CutoverDiagnostic("error", "missing_date", "requirement", identifier, "Date de segment manquante ou invalide."))
        elif row["end_date"] < row["start_date"]:
            diagnostics.append(CutoverDiagnostic("error", "invalid_date_window", "requirement", identifier, "Fenêtre de segment invalide."))
        if row.get("planned_hours") is None or float(row["planned_hours"]) <= 0:
            diagnostics.append(CutoverDiagnostic("error", "invalid_hours", "requirement", identifier, "Heures prévues absentes ou non positives."))

    for row in dataset.shifts:
        identifier = _text(row.get("allocation_id"))
        segment = _text(row.get("segment_id"))
        resource = _text(row.get("resource_name"))
        if segment not in requirement_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_requirement", "shift", identifier, f"Segment inconnu: {segment}"))
        if resource not in resource_ids:
            diagnostics.append(CutoverDiagnostic("error", "unknown_resource", "shift", identifier, f"Ressource inconnue: {resource}"))
        if row.get("work_date") is None:
            diagnostics.append(CutoverDiagnostic("error", "missing_date", "shift", identifier, "Date de quart manquante ou invalide."))
        if row.get("hours") is None or float(row["hours"]) <= 0:
            diagnostics.append(CutoverDiagnostic("error", "invalid_hours", "shift", identifier, "Heures de quart absentes ou non positives."))

    return tuple(diagnostics)


def extract_cutover_dataset(reader: CutoverReader) -> CutoverExtractionReport:
    """Capture and normalize the legacy workbook without performing any write."""

    dataset = CutoverDataset(
        projects=_project_rows(reader.records("Liste des projets", "Numéro de Projet")),
        work_packages=_work_package_rows(reader.records("Liste_Effort", "N° projet")),
        resources=_resource_rows(reader.records("RessourcesMO", "Technicien")),
        availability=_availability_rows(reader.records("Disponibilites", "ID")),
        demands=_demand_rows(reader.records("DemandesMO", "NoDemande")),
        history=_history_rows(reader.records("Historique", "NoDemande")),
        requirements=_requirement_rows(reader.records("SegmentsMO", "IDSegment")),
        shifts=_shift_rows(reader.records("AllocationsMO", "IDAllocation")),
    )
    diagnostics = _validate(dataset)
    locked = [row for row in dataset.shifts if bool(row.get("locked"))]
    counts = {
        "projects": len(dataset.projects),
        "work_packages": len(dataset.work_packages),
        "resources": len(dataset.resources),
        "availability": len(dataset.availability),
        "demands": len(dataset.demands),
        "history": len(dataset.history),
        "requirements": len(dataset.requirements),
        "shifts": len(dataset.shifts),
        "locked_shifts": len(locked),
    }
    hours = {
        "work_package_planned": round(sum(float(row.get("planned_hours") or 0) for row in dataset.work_packages), 4),
        "requirement_planned": round(sum(float(row.get("planned_hours") or 0) for row in dataset.requirements), 4),
        "shift_total": round(sum(float(row.get("hours") or 0) for row in dataset.shifts), 4),
        "locked_shift_total": round(sum(float(row.get("hours") or 0) for row in locked), 4),
    }
    return CutoverExtractionReport(
        dataset=dataset,
        diagnostics=diagnostics,
        counts=counts,
        hours=hours,
    )
