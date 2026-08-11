from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from nicegui import ui

from . import features
from . import ui as ui_module
from . import v13, v14, v14_engine, v14_fixes, v15, v15_engine
from .bugfixes import schedulable_technicians
from .excel_repository import DEMAND_HEADERS, ExcelRepository, _date_from_any
from .services import week_days


DEMAND_CONFIRMATION_FIELD = "Confirmation"
CONFIRMATION_OPTIONS = ["Confirmée", "Tentative"]
SEGMENT_OVERTIME_FIELD = "HorsHoraireAutorise"
MISSING_ALLOCATION_TYPE = "Hors horaire requis"


def demand_confirmation(demand: dict[str, Any] | None) -> str:
    value = str((demand or {}).get(DEMAND_CONFIRMATION_FIELD) or "").strip()
    return value if value in CONFIRMATION_OPTIONS else "Confirmée"


def segment_overtime_allowed(segment: dict[str, Any] | None) -> bool:
    return v15_engine._truthy((segment or {}).get(SEGMENT_OVERTIME_FIELD))


def is_missing_allocation(allocation: dict[str, Any]) -> bool:
    return str(allocation.get("TypeAllocation") or "") == MISSING_ALLOCATION_TYPE


def _request_dialog(self: ui_module.PlannerUI, demand: dict[str, Any] | None = None) -> None:
    self.interaction_lock = True
    editing = demand is not None
    project_options, project_lookup = features._project_data(self.repo)
    competencies = self.repo.competencies()
    technicians = [row["name"] for row in schedulable_technicians(self.repo)]

    initial_project = str(demand.get("NumeroProjet") or "") if demand else None
    if initial_project and initial_project not in project_options:
        project_options[initial_project] = f"{initial_project} — {demand.get('NomProjet') or ''}"

    with ui.dialog() as dialog, ui.card().classes("w-[840px] max-w-full"):
        ui.label(
            f"Modifier {demand.get('NoDemande')}" if editing else "Nouvelle demande de main-d'œuvre"
        ).classes("text-xl font-bold")
        if editing:
            ui.label(f"Statut actuel : {demand.get('Statut') or ''}").classes("text-sm muted")

        project = ui.select(
            project_options,
            label="Projet — taper pour rechercher par numéro, nom ou client",
            value=initial_project,
            with_input=True,
            clearable=True,
        ).classes("w-full")

        with ui.row().classes("w-full"):
            req_type = ui.select(
                ["Service", "Projet", "Interne"],
                label="Type",
                value=(demand.get("TypeDemande") if demand else "Projet") or "Projet",
            ).classes("flex-1")
            priority = ui.select(
                ["Urgent", "Élevée", "Normale", "Basse"],
                label="Priorité",
                value=(demand.get("Priorite") if demand else "Normale") or "Normale",
            ).classes("flex-1")
            confirmation = ui.select(
                CONFIRMATION_OPTIONS,
                label="Niveau de confirmation",
                value=demand_confirmation(demand),
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            start = ui.input(
                "Début souhaité",
                value=self._date_text(demand.get("DateDebutSouhaitee")) if demand else "",
            ).props("type=date").classes("flex-1")
            end = ui.input(
                "Fin souhaitée",
                value=self._date_text(demand.get("DateFinSouhaitee")) if demand else "",
            ).props("type=date").classes("flex-1")

        with ui.row().classes("w-full"):
            competency = ui.select(
                competencies,
                label="Compétence requise",
                value=demand.get("CompetencesRequises") if demand else None,
                with_input=True,
                clearable=True,
            ).classes("flex-1")
            technician = ui.select(
                technicians,
                label="Technicien proposé",
                value=demand.get("TechnicienPropose") if demand else None,
                with_input=True,
                clearable=True,
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            resources = ui.number(
                "Nombre de ressources",
                value=(demand.get("NombreRessources") if demand else 1) or 1,
                min=1,
                step=1,
            ).classes("flex-1")
            hours = ui.number(
                "Temps estimé (h)",
                value=demand.get("TempsEstimeHeures") if demand else None,
                min=0,
                step=1,
            ).classes("flex-1")
            days_count = ui.number(
                "Temps estimé (jours)",
                value=demand.get("TempsEstimeJours") if demand else None,
                min=0,
                step=0.5,
            ).classes("flex-1")

        site = ui.input(
            "Site client / lieu",
            value=str((demand.get("SiteClient") or demand.get("Lieu") or "") if demand else ""),
        ).classes("w-full")
        description = ui.textarea(
            "Description",
            value=str(demand.get("Description") or "") if demand else "",
        ).classes("w-full")

        def payload() -> dict[str, Any]:
            selected = project_lookup.get(str(project.value), {})
            return {
                "NumeroProjet": project.value,
                "NomProjet": selected.get("Nom de référence")
                or selected.get("Description de l'appel d'offre")
                or (demand.get("NomProjet") if demand else "")
                or "",
                "Client": selected.get("Donneur d'ouvrage")
                or (demand.get("Client") if demand else "")
                or "",
                "ChargeProjet": selected.get("Chargé de projet")
                or (demand.get("ChargeProjet") if demand else "")
                or "",
                "TypeDemande": req_type.value,
                "Priorite": priority.value,
                DEMAND_CONFIRMATION_FIELD: confirmation.value or "Confirmée",
                "DateDebutSouhaitee": start.value,
                "DateFinSouhaitee": end.value,
                "Description": description.value,
                "SiteClient": site.value,
                "Lieu": site.value,
                "NombreRessources": resources.value,
                "CompetencesRequises": competency.value,
                "TempsEstimeHeures": hours.value,
                "TempsEstimeJours": days_count.value,
                "TechnicienPropose": technician.value,
            }

        def validate() -> bool:
            if not project.value or not start.value:
                ui.notify("Projet et date de début sont requis.", type="warning")
                return False
            start_date = _date_from_any(start.value)
            end_date = _date_from_any(end.value)
            if start_date and end_date and end_date < start_date:
                ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                return False
            return True

        def save_edit() -> None:
            if not validate():
                return
            try:
                self.repo.update_demand(
                    str(demand["NoDemande"]),
                    payload(),
                    action="Modification",
                    comment="Demande modifiée dans l'application",
                )
                dialog.close()
                self._after_write("Demande mise à jour")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def save_draft() -> None:
            if not validate():
                return
            try:
                number = self.repo.create_demand(payload(), submit=False)
                dialog.close()
                self._after_write(f"{number} enregistré comme brouillon")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def submit_new() -> None:
            if not validate():
                return
            try:
                number = self.repo.create_demand(payload(), submit=True)
                dialog.close()
                self._after_write(f"{number} soumise pour approbation")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if editing:
                ui.button("Enregistrer", icon="save", on_click=save_edit).props(
                    "unelevated no-caps color=primary"
                )
            else:
                ui.button("Brouillon", icon="save", on_click=save_draft).props("outline no-caps")
                ui.button("Soumettre", icon="send", on_click=submit_new).props(
                    "unelevated no-caps color=primary"
                )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _segment_dialog(
    self: ui_module.PlannerUI,
    segment: dict[str, Any] | None = None,
    demand_number: str | None = None,
) -> None:
    self.interaction_lock = True
    editing = segment is not None
    demands = {str(row.get("NoDemande") or ""): row for row in self.repo.demands()}
    selected_number = str(segment.get("NoDemande") or "") if segment else str(demand_number or "")
    demand_options = v13._demand_options(self.repo)
    current_demand = demands.get(selected_number, {})

    tech_options = [row["name"] for row in schedulable_technicians(self.repo)]
    competence_options = list(self.repo.competencies())
    effort_options = v13._effort_options(self.repo, current_demand.get("NumeroProjet"))
    inherited_source = v13._source_effort_for_demand(current_demand) if current_demand else None

    source_value: Any = inherited_source
    if segment and segment.get("SourceEffortRow") not in (None, ""):
        try:
            source_value = str(int(float(segment.get("SourceEffortRow"))))
        except (TypeError, ValueError):
            source_value = str(segment.get("SourceEffortRow"))
    if source_value and source_value not in effort_options:
        effort_options.update(v13._effort_options(self.repo))

    initial_competence = (
        str(segment.get("CompetenceRequise") or "")
        if segment
        else str(current_demand.get("CompetencesRequises") or "")
    ) or None
    if initial_competence and initial_competence not in competence_options:
        competence_options.append(initial_competence)

    initial_tech = (
        str(segment.get("Technicien") or "")
        if segment
        else str(current_demand.get("TechnicienPropose") or "")
    ).strip()
    initial_tech = initial_tech if initial_tech in tech_options else None

    with ui.dialog() as dialog, ui.card().classes("w-[840px] max-w-full"):
        ui.label(
            f"Modifier {segment.get('IDSegment')}" if editing else "Nouveau segment"
        ).classes("text-xl font-bold")
        ui.label(
            "Le technicien est facultatif. Le travail hors horaire au niveau du segment autorise le moteur à placer le reliquat en soirée, fin de semaine ou jour férié."
        ).classes("text-xs muted")

        demand_select = ui.select(
            demand_options,
            label="Demande MO",
            value=selected_number or None,
            with_input=True,
            clearable=False,
        ).classes("w-full")
        if selected_number:
            demand_select.props("readonly")

        with ui.row().classes("w-full"):
            technician = ui.select(
                tech_options,
                label="Technicien (optionnel)",
                value=initial_tech,
                with_input=True,
                clearable=True,
            ).classes("flex-1")
            competence = ui.select(
                competence_options,
                label="Compétence requise",
                value=initial_competence,
                with_input=True,
                clearable=True,
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            planning_type = ui.select(
                v14.PLAN_TYPES,
                label="Type de planification",
                value=v14_engine.segment_plan_type(segment or {}),
            ).classes("flex-1")
            priority = ui.select(
                v14.PRIORITIES,
                label="Priorité",
                value=(str(segment.get("Priorite") or "") if segment else str(current_demand.get("Priorite") or "Normale")) or "Normale",
            ).classes("flex-1")
            status = ui.select(
                v13.SEGMENT_STATUSES,
                label="Statut",
                value=(str(segment.get("Statut") or "") if segment else ("Planifié" if initial_tech else "À assigner")) or "À assigner",
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            start = ui.input(
                "Début",
                value=self._date_text(segment.get("DateDebut")) if segment else self._date_text(current_demand.get("DateDebutSouhaitee")),
            ).props("type=date").classes("flex-1")
            end = ui.input(
                "Fin",
                value=self._date_text(segment.get("DateFin")) if segment else self._date_text(current_demand.get("DateFinSouhaitee")),
            ).props("type=date").classes("flex-1")
            hours = ui.number(
                "Heures prévues",
                value=v13._number(segment.get("HeuresPrevues")) if segment else (v13._number(current_demand.get("TempsEstimeHeures")) or None),
                min=0.5,
                step=0.5,
            ).classes("flex-1")

        overtime_allowed = ui.checkbox(
            "Autoriser le segment à utiliser du travail hors horaire standard si la capacité normale est insuffisante",
            value=segment_overtime_allowed(segment),
        )

        source = ui.select(
            effort_options,
            label="Planification moyen terme liée (optionnel)",
            value=source_value,
            with_input=True,
            clearable=True,
        ).classes("w-full")
        description = ui.input(
            "Description / précision",
            value=str(segment.get("Description") or "") if segment else str(current_demand.get("Description") or ""),
        ).classes("w-full")

        def validate() -> bool:
            if not demand_select.value:
                ui.notify("Sélectionne une demande.", type="warning")
                return False
            start_date = _date_from_any(start.value)
            end_date = _date_from_any(end.value) or start_date
            if not start_date:
                ui.notify("La date de début est requise.", type="warning")
                return False
            if end_date and end_date < start_date:
                ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                return False
            if v13._number(hours.value) <= 0:
                ui.notify("Les heures prévues doivent être supérieures à zéro.", type="warning")
                return False
            if not competence.value:
                ui.notify("La compétence requise est nécessaire.", type="warning")
                return False
            return True

        def build_payload() -> dict[str, Any]:
            demand = demands.get(str(demand_select.value or ""), {})
            source_row: Any = source.value
            if source_row not in (None, ""):
                try:
                    source_row = int(float(source_row))
                except (TypeError, ValueError):
                    pass
            tech = str(technician.value or "").strip()
            chosen_status = str(status.value or "")
            if not tech and chosen_status not in {"Annulé", "Terminé"}:
                chosen_status = "À assigner"
            elif tech and chosen_status == "À assigner":
                chosen_status = "Planifié"
            return {
                "NoDemande": demand_select.value,
                "NumeroProjet": demand.get("NumeroProjet"),
                "NomProjet": demand.get("NomProjet"),
                "Technicien": tech or None,
                "DateDebut": start.value,
                "DateFin": end.value or start.value,
                "HeuresPrevues": hours.value,
                "Statut": chosen_status,
                "Description": description.value,
                "SourceEffortRow": source_row,
                "CompetenceRequise": competence.value,
                "TypePlanification": planning_type.value or "Flexible",
                "Priorite": priority.value or "Normale",
                SEGMENT_OVERTIME_FIELD: "Oui" if overtime_allowed.value else "Non",
            }

        def save() -> None:
            if not validate():
                return
            try:
                data = build_payload()
                if editing:
                    v13.update_segment(self.repo, str(segment["IDSegment"]), data)
                    message = f"{segment['IDSegment']} mis à jour"
                else:
                    ident = v13.add_segment(self.repo, data)
                    message = f"{ident} créé"
                summary = rebuild_allocations_refined(self.repo)
                dialog.close()
                if summary["unallocated_hours"] > 0:
                    message += f" · {summary['unallocated_hours']:g} h nécessitent du hors horaire"
                self._after_write(message)
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def cancel_segment() -> None:
            try:
                v13.update_segment(self.repo, str(segment["IDSegment"]), {"Statut": "Annulé"})
                rebuild_allocations_refined(self.repo)
                dialog.close()
                self._after_write(f"{segment['IDSegment']} annulé")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if editing and str(segment.get("Statut") or "") != "Annulé":
                ui.button("Annuler le segment", icon="cancel", on_click=cancel_segment).props(
                    "flat no-caps color=negative"
                )
            ui.button("Enregistrer", icon="save", on_click=save).props(
                "unelevated no-caps color=primary"
            )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _overtime_slots(repo: ExcelRepository, technician: str, segment: dict[str, Any], hours: float) -> list[tuple[date, float]]:
    start, end = v13._segment_dates(segment)
    if not start or not end or hours <= 0:
        return []
    candidates: list[tuple[int, date]] = []
    cursor = start
    while cursor <= end:
        state = features.availability_for_day(repo, technician, cursor)
        reason = f"{state.get('reason') or ''} {state.get('type') or ''}".lower()
        if "vacance" not in reason:
            # Priorité aux journées sans horaire normal (week-end / férié), puis aux soirées de semaine.
            priority = 0 if v13._availability_hours(repo, technician, cursor) <= 0 else 1
            candidates.append((priority, cursor))
        cursor += timedelta(days=1)
    candidates.sort(key=lambda item: (item[0], item[1]))
    remaining = hours
    result: list[tuple[date, float]] = []
    for _, day in candidates:
        if remaining <= 0.001:
            break
        amount = min(8.0, remaining)
        result.append((day, round(amount, 2)))
        remaining -= amount
    return result


def _auto_payload(
    segment: dict[str, Any],
    day: date,
    hours: float,
    allocation_type: str,
    competence: str,
    priority: str,
    sequence: int,
    generation: datetime,
    *,
    hors_horaire: str = "Non",
    note: str = "",
) -> dict[str, Any]:
    row = v14_engine._payload(
        segment, day, hours, allocation_type, competence, priority, sequence, generation
    )
    row["Verrouillee"] = "Non"
    row["HorsHoraire"] = hors_horaire
    row["Note"] = note
    return row


def rebuild_allocations_refined(repo: ExcelRepository) -> dict[str, Any]:
    """Recalcule les quarts en distinguant capacité normale, hors horaire réel et manque proposé."""
    with repo._lock:
        v15_engine.ensure_v15_sheets(repo)
        demands = v14_engine.demand_lookup(repo)
        schedulable = {row["name"] for row in schedulable_technicians(repo)}
        active_segments = [
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("Statut") or "") not in {"Annulé", "Terminé"}
        ]
        segment_map = {str(row.get("IDSegment") or ""): row for row in active_segments}

        preserved: list[dict[str, Any]] = []
        locked_by_segment: dict[str, float] = {}
        locked_used: dict[tuple[str, date], float] = {}
        for row in v15_engine.allocation_records(repo):
            if not v15_engine._truthy(row.get("Verrouillee")):
                continue
            segment_id = str(row.get("IDSegment") or "")
            if segment_id not in segment_map:
                continue
            day = _date_from_any(row.get("Date"))
            tech = str(row.get("Technicien") or "").strip()
            hours = v13._number(row.get("Heures"))
            if not day or not tech or hours <= 0:
                continue
            clean = dict(row)
            clean["Date"] = day
            clean["Heures"] = round(hours, 2)
            clean["Verrouillee"] = "Oui"
            clean["HorsHoraire"] = "Oui" if v15_engine._truthy(row.get("HorsHoraire")) else "Non"
            preserved.append(clean)
            locked_by_segment[segment_id] = locked_by_segment.get(segment_id, 0.0) + hours
            locked_used[(tech, day)] = locked_used.get((tech, day), 0.0) + hours

        segments = [
            row
            for row in active_segments
            if str(row.get("Technicien") or "").strip() in schedulable
            and v13._number(row.get("HeuresPrevues")) > 0
        ]
        fixed = sorted(
            [row for row in segments if v14_engine.segment_plan_type(row) == "Fixe"],
            key=lambda row: v14_engine._segment_sort_key(row, demands),
        )
        flexible = sorted(
            [row for row in segments if v14_engine.segment_plan_type(row) != "Fixe"],
            key=lambda row: v14_engine._segment_sort_key(row, demands),
        )

        raw_capacity: dict[tuple[str, date], float] = {}
        normal_used: dict[tuple[str, date], float] = dict(locked_used)
        rows: list[dict[str, Any]] = list(preserved)
        generation = datetime.now()
        sequence = 0
        missing_total = 0.0
        overtime_total = sum(
            v13._number(row.get("Heures"))
            for row in preserved
            if v15_engine._truthy(row.get("HorsHoraire"))
        )

        def capacity(technician: str, day: date) -> float:
            key = (technician, day)
            if key not in raw_capacity:
                raw_capacity[key] = v13._availability_hours(repo, technician, day)
            return raw_capacity[key]

        def place_segment(segment: dict[str, Any], allocation_type: str) -> None:
            nonlocal sequence, missing_total, overtime_total
            tech = str(segment.get("Technicien") or "").strip()
            segment_id = str(segment.get("IDSegment") or "")
            remaining_hours = max(
                v13._number(segment.get("HeuresPrevues")) - locked_by_segment.get(segment_id, 0.0),
                0.0,
            )
            if remaining_hours <= 0:
                return
            start, end = v13._segment_dates(segment)
            if not start or not end:
                return

            residual: list[tuple[date, float]] = []
            cursor = start
            while cursor <= end:
                room = max(capacity(tech, cursor) - normal_used.get((tech, cursor), 0.0), 0.0)
                if room > 0:
                    residual.append((cursor, room))
                cursor += timedelta(days=1)

            spread = v14_engine._spread_hours(remaining_hours, residual)
            competence = v14_engine.segment_competence(segment, demands)
            priority = v14_engine.segment_priority(segment, demands)
            for day, amount in spread.items():
                sequence += 1
                normal_used[(tech, day)] = normal_used.get((tech, day), 0.0) + amount
                rows.append(
                    _auto_payload(
                        segment,
                        day,
                        amount,
                        allocation_type,
                        competence,
                        priority,
                        sequence,
                        generation,
                    )
                )

            missing = max(remaining_hours - sum(spread.values()), 0.0)
            if missing <= 0.001:
                return

            allowed = segment_overtime_allowed(segment)
            slots = _overtime_slots(repo, tech, segment, missing)
            placed_overtime = 0.0
            for day, amount in slots:
                sequence += 1
                placed_overtime += amount
                rows.append(
                    _auto_payload(
                        segment,
                        day,
                        amount,
                        allocation_type if allowed else MISSING_ALLOCATION_TYPE,
                        competence,
                        priority,
                        sequence,
                        generation,
                        hors_horaire="Oui" if allowed else "Requis",
                        note=(
                            "Hors horaire autorisé au niveau du segment"
                            if allowed
                            else "Capacité standard insuffisante — quart hors horaire à confirmer"
                        ),
                    )
                )
            residual_missing = max(missing - placed_overtime, 0.0)
            if allowed:
                overtime_total += placed_overtime
                missing_total += residual_missing
            else:
                missing_total += missing

        for segment in fixed:
            place_segment(segment, "Fixe")
        for segment in flexible:
            place_segment(segment, "Flexible")

        rows.sort(
            key=lambda row: (
                str(row.get("Technicien") or ""),
                _date_from_any(row.get("Date")) or date.max,
                0 if v15_engine._truthy(row.get("Verrouillee")) else 1,
                str(row.get("TypeAllocation") or ""),
                str(row.get("IDSegment") or ""),
            )
        )
        v15_engine._write_allocations(repo, rows)

        actual_rows = [row for row in rows if not is_missing_allocation(row)]
        requested = sum(v13._number(row.get("HeuresPrevues")) for row in segments)
        allocated = sum(v13._number(row.get("Heures")) for row in actual_rows)
        return {
            "segments": len(segments),
            "allocations": len(actual_rows),
            "locked_allocations": len(preserved),
            "requested_hours": round(requested, 2),
            "allocated_hours": round(allocated, 2),
            "overtime_hours": round(overtime_total, 2),
            "unallocated_hours": round(max(requested - allocated, missing_total), 2),
        }


def weekly_allocation_load_refined(repo: ExcelRepository, start: date) -> list[dict[str, Any]]:
    techs = {row["name"]: row for row in schedulable_technicians(repo)}
    end = start + timedelta(days=6)
    allocations = [
        row
        for row in v15_engine.allocation_records(repo)
        if row.get("Date") and start <= row["Date"] <= end and not is_missing_allocation(row)
    ]
    result: list[dict[str, Any]] = []
    for name, info in techs.items():
        capacity = sum(v13._availability_hours(repo, name, start + timedelta(days=index)) for index in range(7))
        own = [row for row in allocations if str(row.get("Technicien") or "").strip() == name]
        planned = sum(v13._number(row.get("Heures")) for row in own)
        overtime = sum(
            v13._number(row.get("Heures")) for row in own if v15_engine._truthy(row.get("HorsHoraire"))
        )
        pct = round(planned / capacity * 100, 0) if capacity else None
        result.append(
            {
                "name": name,
                "planned": round(planned, 1),
                "weekly_capacity": round(capacity, 1),
                "overtime": round(overtime, 1),
                "available": round(max(capacity - planned, 0.0), 1),
                "pct": pct,
                "team": info.get("team") or "",
                "description": info.get("description") or "",
            }
        )
    result.sort(key=lambda row: (-(row["pct"] or -1), row["name"]))
    return result


def allocated_by_segment_refined(repo: ExcelRepository) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in v15_engine.allocation_records(repo):
        if is_missing_allocation(row):
            continue
        ident = str(row.get("IDSegment") or "")
        result[ident] = result.get(ident, 0.0) + v13._number(row.get("Heures"))
    return result


def _sync_segments_to_approved_demand(repo: ExcelRepository, demand: dict[str, Any]) -> None:
    """Après réapprobation, aligne les segments sur la nouvelle version approuvée."""
    number = str(demand.get("NoDemande") or "")
    desired = max(int(v13._number(demand.get("NombreRessources")) or 1), 1)
    per_resource = v15._estimated_hours_per_resource(repo, demand, desired)
    current = [
        row
        for row in v13.segment_records(repo, include_cancelled=False)
        if str(row.get("NoDemande") or "") == number and str(row.get("Statut") or "") != "Annulé"
    ]

    while len(current) < desired:
        ident = v13.add_segment(
            repo,
            {
                "NoDemande": number,
                "NumeroProjet": demand.get("NumeroProjet"),
                "NomProjet": demand.get("NomProjet"),
                "Technicien": None,
                "DateDebut": demand.get("DateDebutSouhaitee"),
                "DateFin": demand.get("DateFinSouhaitee") or demand.get("DateDebutSouhaitee"),
                "HeuresPrevues": per_resource,
                "Statut": "À assigner",
                "Description": demand.get("Description") or "Ressource additionnelle",
                "SourceEffortRow": demand.get(v13.SOURCE_EFFORT_FIELD),
                "CompetenceRequise": demand.get("CompetencesRequises"),
                "TypePlanification": "Flexible",
                "Priorite": demand.get("Priorite") or "Normale",
                SEGMENT_OVERTIME_FIELD: "Non",
            },
        )
        current = [
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("NoDemande") or "") == number and str(row.get("Statut") or "") != "Annulé"
        ]
        if not any(str(row.get("IDSegment") or "") == ident for row in current):
            break

    if len(current) > desired:
        # Conserve d'abord les segments déjà assignés; annule les excédents, en priorité non assignés.
        ranked = sorted(
            current,
            key=lambda row: (0 if str(row.get("Technicien") or "").strip() else 1, int(row.get("_row") or 0)),
        )
        keep_ids = {str(row.get("IDSegment") or "") for row in ranked[:desired]}
        for row in current:
            if str(row.get("IDSegment") or "") not in keep_ids:
                v13.update_segment(repo, str(row.get("IDSegment") or ""), {"Statut": "Annulé"})
        current = [row for row in ranked if str(row.get("IDSegment") or "") in keep_ids]

    proposed = str(demand.get("TechnicienPropose") or "").strip()
    source = demand.get(v13.SOURCE_EFFORT_FIELD)
    for index, row in enumerate(current[:desired]):
        tech = str(row.get("Technicien") or "").strip()
        if index == 0 and not tech and proposed:
            tech = proposed
        current_type = str(row.get("TypePlanification") or "Flexible") or "Flexible"
        current_overtime = row.get(SEGMENT_OVERTIME_FIELD)
        status = str(row.get("Statut") or "")
        if tech and status == "À assigner":
            status = "Planifié"
        if not tech and status not in {"Terminé", "Annulé"}:
            status = "À assigner"
        v13.update_segment(
            repo,
            str(row.get("IDSegment") or ""),
            {
                "NumeroProjet": demand.get("NumeroProjet"),
                "NomProjet": demand.get("NomProjet"),
                "Technicien": tech or None,
                "DateDebut": demand.get("DateDebutSouhaitee"),
                "DateFin": demand.get("DateFinSouhaitee") or demand.get("DateDebutSouhaitee"),
                "HeuresPrevues": per_resource,
                "Statut": status,
                "Description": demand.get("Description") or row.get("Description") or "",
                "SourceEffortRow": source,
                "CompetenceRequise": demand.get("CompetencesRequises"),
                "TypePlanification": current_type,
                "Priorite": demand.get("Priorite") or "Normale",
                SEGMENT_OVERTIME_FIELD: current_overtime or "Non",
            },
        )

    repo.log_history(
        number,
        "Synchronisation segments",
        "En planification",
        "En planification",
        f"Segments synchronisés avec la version approuvée ({desired} ressource(s)).",
    )


def _allocation_style(allocation: dict[str, Any], demand: dict[str, Any], overloaded: bool) -> tuple[str, str]:
    if is_missing_allocation(allocation):
        return (
            "background:#fff7ed;border:2px dashed #f97316;opacity:.92;",
            "Hors horaire requis",
        )
    tentative = demand_confirmation(demand) == "Tentative"
    if v15_engine._truthy(allocation.get("HorsHoraire")):
        return "background:#ffedd5;border-left:4px solid #ea580c;", "Hors horaire"
    if overloaded:
        return "background:#fee2e2;border-left:4px solid #dc2626;", "Surchargé"
    if tentative:
        return "background:#fef3c7;border:2px dashed #d97706;", "Tentative"
    if v15_engine._truthy(allocation.get("Verrouillee")) or str(allocation.get("TypeAllocation") or "") == "Fixe":
        return "background:#ede9fe;border-left:4px solid #7c3aed;", "Fixe / verrouillé"
    return "background:#dbeafe;border-left:4px solid #2563eb;", "Flexible"


def _open_allocation_dialog(
    self: ui_module.PlannerUI,
    allocation: dict[str, Any] | None = None,
    segment: dict[str, Any] | None = None,
    default_date: date | None = None,
) -> None:
    if allocation and is_missing_allocation(allocation):
        segment_id = str(allocation.get("IDSegment") or "")
        target = next(
            (row for row in v13.segment_records(self.repo, include_cancelled=False) if str(row.get("IDSegment") or "") == segment_id),
            None,
        )
        if target:
            _segment_dialog(self, segment=target)
        return

    self.interaction_lock = True
    editing = allocation is not None
    segments = [row for row in v13.segment_records(self.repo, include_cancelled=False) if str(row.get("Statut") or "") not in {"Annulé", "Terminé"}]
    segment_lookup = {str(row.get("IDSegment") or ""): row for row in segments}
    segment_options = {
        str(row.get("IDSegment") or ""): f"{row.get('IDSegment')} — {row.get('NumeroProjet') or '—'} · {row.get('NomProjet') or ''}"
        for row in segments if row.get("IDSegment")
    }
    initial_segment_id = str((allocation or {}).get("IDSegment") or (segment or {}).get("IDSegment") or "")
    initial_segment = segment_lookup.get(initial_segment_id, segment or {})
    tech_options = [row["name"] for row in schedulable_technicians(self.repo)]
    initial_tech = str((allocation or {}).get("Technicien") or initial_segment.get("Technicien") or "").strip()
    if initial_tech and initial_tech not in tech_options:
        tech_options.append(initial_tech)
    initial_day = _date_from_any((allocation or {}).get("Date")) or default_date or _date_from_any(initial_segment.get("DateDebut")) or self.current_week

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label("Modifier / verrouiller le quart" if editing else "Nouveau quart manuel").classes("text-xl font-bold")
        segment_select = ui.select(segment_options, label="Segment", value=initial_segment_id or None, with_input=True).classes("w-full")
        if editing:
            segment_select.props("readonly")
        with ui.row().classes("w-full"):
            technician = ui.select(tech_options, label="Technicien", value=initial_tech or None, with_input=True).classes("flex-1")
            day = ui.input("Date", value=initial_day.isoformat() if initial_day else "").props("type=date").classes("flex-1")
            hours = ui.number("Heures", value=v13._number((allocation or {}).get("Heures")) or None, min=0.25, step=0.25).classes("flex-1")
        hors_horaire = ui.checkbox(
            "Autoriser explicitement ce quart hors horaire standard",
            value=v15_engine._truthy((allocation or {}).get("HorsHoraire")),
        )
        note = ui.input("Note", value=str((allocation or {}).get("Note") or "")).classes("w-full")

        def open_segment() -> None:
            target = segment_lookup.get(str(segment_select.value or ""))
            dialog.close()
            if target:
                ui.timer(0.05, lambda: _segment_dialog(self, segment=target), once=True)

        def save() -> None:
            if not segment_select.value or not technician.value or not day.value:
                ui.notify("Segment, technicien et date sont requis.", type="warning")
                return
            try:
                if editing:
                    v15_engine.update_manual_allocation(
                        self.repo,
                        str(allocation.get("IDAllocation") or ""),
                        str(technician.value),
                        day.value,
                        hours.value,
                        bool(hors_horaire.value),
                        str(note.value or ""),
                    )
                    message = "Quart verrouillé et mis à jour"
                else:
                    v15_engine.create_manual_allocation(
                        self.repo,
                        str(segment_select.value),
                        str(technician.value),
                        day.value,
                        hours.value,
                        bool(hors_horaire.value),
                        str(note.value or ""),
                    )
                    message = "Quart manuel créé"
                dialog.close()
                self._after_write(message)
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def release() -> None:
            try:
                v15_engine.release_manual_allocation(self.repo, str(allocation.get("IDAllocation") or ""))
                dialog.close()
                self._after_write("Quart remis en planification automatique")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def delete() -> None:
            try:
                v15_engine.delete_manual_allocation(self.repo, str(allocation.get("IDAllocation") or ""))
                dialog.close()
                self._after_write("Quart manuel supprimé; le reliquat a été recalculé")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Fermer", on_click=dialog.close).props("flat no-caps")
            ui.button("Modifier le segment", icon="view_timeline", on_click=open_segment).props("outline no-caps")
            if editing and v15_engine._truthy(allocation.get("Verrouillee")):
                ui.button("Revenir à l'automatique", icon="autorenew", on_click=release).props("outline no-caps")
                ui.button("Supprimer le quart", icon="delete", on_click=delete).props("flat no-caps color=negative")
            ui.button("Enregistrer et verrouiller", icon="lock", on_click=save).props("unelevated no-caps color=primary")

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _render_planning(self: ui_module.PlannerUI) -> None:
    days = week_days(self.current_week)
    techs = schedulable_technicians(self.repo)
    allocations = [
        row for row in v15_engine.allocation_records(self.repo)
        if row.get("Date") and days[0] <= row["Date"] <= days[-1]
    ]
    segments = {str(row.get("IDSegment") or ""): row for row in v13.segment_records(self.repo, include_cancelled=False)}
    demands = v14_engine.demand_lookup(self.repo)
    unassigned = v15._unassigned_segments_for_week(self.repo, self.current_week)
    pending = v15._pending_demands_for_week(self.repo, self.current_week)

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planning opérationnel").classes("text-2xl font-bold")
            ui.label(
                "Bleu = flexible · violet = fixe/verrouillé · jaune = tentative · rouge = surcharge · orange = hors horaire · orange pointillé = hors horaire requis · gris = attente d'approbation."
            ).classes("muted")
        ui.space()
        ui.button("Quart manuel", icon="add_task", on_click=lambda: _open_allocation_dialog(self)).props("outline no-caps")
        ui.button("Recalculer", icon="calculate", on_click=lambda: _recalculate(self)).props("outline no-caps")
        ui.button(icon="chevron_left", on_click=self.previous_week).props("flat round")
        ui.button("Aujourd'hui", on_click=self.today_week).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=self.next_week).props("flat round")
        ui.label(f"{days[0].strftime('%d %b')} – {days[-1].strftime('%d %b %Y')}").classes("font-semibold ml-2")

    if unassigned:
        with ui.card().classes("section-card w-full"):
            ui.label(f"Travaux à planifier cette semaine ({len(unassigned)})").classes("text-lg font-semibold")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for segment in unassigned[:16]:
                    competence = v14_engine.segment_competence(segment, demands) or "Compétence non précisée"
                    with ui.card().classes("p-3 min-w-[250px] max-w-[340px]"):
                        ui.label(f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''}").classes("text-sm font-semibold")
                        ui.label(str(segment.get("Description") or "")).classes("text-xs")
                        ui.label(f"{competence} · {v13._number(segment.get('HeuresPrevues')):g} h").classes("text-xs text-orange-700")
                        ui.button("Ouvrir le segment", icon="view_timeline", on_click=lambda s=segment: _segment_dialog(self, segment=s)).props("flat dense no-caps")

    if pending:
        with ui.card().classes("section-card w-full"):
            ui.label(f"En attente d'approbation dans cette semaine ({len(pending)})").classes("text-lg font-semibold")
            ui.label("Ces besoins sont visibles, mais comptent 0 h de charge.").classes("text-xs muted")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for demand in pending[:16]:
                    tentative = demand_confirmation(demand) == "Tentative"
                    style = "background:#fffbeb;border:2px dashed #d97706;" if tentative else "background:#f9fafb;border:1px dashed #9ca3af;"
                    with ui.card().classes("p-3 min-w-[250px] max-w-[340px]").style(style):
                        ui.label(f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}").classes("text-sm font-semibold")
                        ui.label(f"{demand_confirmation(demand)} · {demand.get('CompetencesRequises') or 'Compétence non précisée'}").classes("text-xs")
                        ui.label(f"{self._date_text(demand.get('DateDebutSouhaitee'))} → {self._date_text(demand.get('DateFinSouhaitee'))}").classes("text-xs muted")

    with ui.scroll_area().classes("w-full h-[calc(100vh-310px)]"):
        with ui.grid(columns=8).classes("schedule-grid gap-0"):
            with ui.column().classes("day-header p-3 justify-center"):
                ui.label("Ressource").classes("font-semibold")
            for day in days:
                with ui.column().classes("day-header p-2 items-center justify-center"):
                    ui.label(day.strftime("%a").capitalize()).classes("text-xs uppercase muted")
                    ui.label(day.strftime("%d")).classes("text-xl font-semibold")

            for tech in techs:
                name = tech["name"]
                with ui.column().classes("resource-cell p-3 justify-center gap-1"):
                    ui.label(name).classes("font-semibold")
                    details = " · ".join(value for value in [tech.get("description"), tech.get("team")] if value)
                    ui.label(details or "Ressource").classes("text-xs muted")

                for day in days:
                    state = features.availability_for_day(self.repo, name, day)
                    day_capacity = v13._availability_hours(self.repo, name, day)
                    day_allocations = [
                        row for row in allocations
                        if str(row.get("Technicien") or "").strip() == name and row.get("Date") == day
                    ]
                    actual_allocations = [row for row in day_allocations if not is_missing_allocation(row)]
                    pending_day = [
                        row for row in pending
                        if str(row.get("TechnicienPropose") or "").strip() == name
                        and v15._pending_covers_day(row, day)
                        and v13._availability_hours(self.repo, name, day) > 0
                    ]
                    planned = sum(v13._number(row.get("Heures")) for row in actual_allocations)
                    overloaded = planned > day_capacity + 0.01 and day_capacity >= 0
                    classes = "day-cell gap-1"
                    if not state.get("available"):
                        classes += " unavailable-cell"
                    elif day.weekday() >= 5:
                        classes += " weekend-cell"

                    with ui.column().classes(classes):
                        if state.get("available") and state.get("hours"):
                            ui.label(state["hours"]).classes("text-[10px] availability-hours")
                        elif not state.get("available"):
                            ui.label(str(state.get("reason") or "Indisponible")).classes("text-[10px] unavailable-label")
                        if planned > 0 or day_capacity > 0:
                            css = "text-[10px] text-red-700 font-semibold" if overloaded else "text-[10px] muted"
                            ui.label(f"{planned:.1f}/{day_capacity:.1f} h").classes(css)

                        for allocation in day_allocations:
                            segment = segments.get(str(allocation.get("IDSegment") or ""), {})
                            demand = demands.get(str(allocation.get("NoDemande") or ""), {})
                            style, label = _allocation_style(allocation, demand, overloaded)
                            with ui.element("div").classes("shift-card").style(style).on(
                                "click", lambda _, a=allocation: _open_allocation_dialog(self, allocation=a)
                            ):
                                ui.label(f"{allocation.get('NumeroProjet') or '—'} · {allocation.get('NomProjet') or ''}").classes("text-xs font-semibold")
                                ui.label(str(segment.get("Description") or allocation.get("IDSegment") or "Allocation")).classes("text-xs")
                                suffix = " · 🔒" if v15_engine._truthy(allocation.get("Verrouillee")) else ""
                                if demand_confirmation(demand) == "Tentative" and "Tentative" not in label:
                                    label = f"Tentative · {label}"
                                ui.label(f"{v13._number(allocation.get('Heures')):.1f} h · {label}{suffix}").classes("text-[11px] muted")

                        for demand in pending_day:
                            tentative = demand_confirmation(demand) == "Tentative"
                            style = "background:#fffbeb;border:2px dashed #d97706;opacity:.95;" if tentative else "background:#f3f4f6;border:2px dashed #9ca3af;opacity:.9;"
                            with ui.element("div").classes("shift-card").style(style):
                                ui.label(f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}").classes("text-xs font-semibold")
                                ui.label(str(demand.get("Description") or "")).classes("text-xs")
                                ui.label(f"{demand_confirmation(demand)} · en attente d'approbation · 0 h").classes("text-[11px] text-gray-600")


def _recalculate(self: ui_module.PlannerUI) -> None:
    try:
        summary = rebuild_allocations_refined(self.repo)
        self._after_write(
            f"Allocations recalculées : {summary['allocated_hours']:g} h allouées"
            + (f" · {summary['overtime_hours']:g} h hors horaire" if summary.get("overtime_hours") else "")
            + (f" · {summary['unallocated_hours']:g} h à confirmer hors horaire" if summary["unallocated_hours"] > 0 else "")
        )
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def install_v15_refinements() -> None:
    if getattr(ui_module.PlannerUI, "_v15_refinements_installed", False):
        return

    if DEMAND_CONFIRMATION_FIELD not in DEMAND_HEADERS:
        DEMAND_HEADERS.append(DEMAND_CONFIRMATION_FIELD)
    if SEGMENT_OVERTIME_FIELD not in v13.SEGMENT_HEADERS:
        v13.SEGMENT_HEADERS.append(SEGMENT_OVERTIME_FIELD)
    if SEGMENT_OVERTIME_FIELD not in v14.SEGMENT_EXTRA_HEADERS:
        v14.SEGMENT_EXTRA_HEADERS.append(SEGMENT_OVERTIME_FIELD)
    v15.BUSINESS_DEMAND_FIELDS.add(DEMAND_CONFIRMATION_FIELD)

    # Les formulaires exposent les nouveaux champs.
    ui_module.PlannerUI.open_new_request_dialog = lambda self: _request_dialog(self)
    ui_module.PlannerUI.open_edit_request_dialog = lambda self, demand: _request_dialog(self, demand)
    features._open_request_dialog = _request_dialog
    v14._open_segment_dialog_v14 = _segment_dialog
    v13._open_segment_dialog = _segment_dialog

    # Le moteur raffiné devient la cible de tous les appels V1.4/V1.5 au runtime.
    v15_engine.rebuild_allocations = rebuild_allocations_refined
    v15_engine.weekly_allocation_load = weekly_allocation_load_refined
    v14_engine.rebuild_allocations = rebuild_allocations_refined
    v14_engine.weekly_allocation_load = weekly_allocation_load_refined
    v14_engine.allocated_by_segment = allocated_by_segment_refined
    v14.rebuild_allocations = rebuild_allocations_refined
    v14.weekly_allocation_load = weekly_allocation_load_refined
    v14.allocated_by_segment = allocated_by_segment_refined
    v14_fixes.rebuild_allocations = rebuild_allocations_refined
    v15.rebuild_allocations = rebuild_allocations_refined
    v15.weekly_allocation_load = weekly_allocation_load_refined
    v15._open_manual_allocation_dialog = _open_allocation_dialog

    # Après une nouvelle approbation, les segments représentent la nouvelle version approuvée.
    original_approve = ExcelRepository.approve_demand

    def approve_demand_refined(self: ExcelRepository, number: str, comment: str = "") -> None:
        original_approve(self, number, comment)
        demand = next(
            (row for row in self.demands() if str(row.get("NoDemande") or "") == str(number)),
            None,
        )
        if demand:
            _sync_segments_to_approved_demand(self, demand)
        rebuild_allocations_refined(self)

    ExcelRepository.approve_demand = approve_demand_refined

    ui_module.PlannerUI.render_planning = _render_planning
    v13._render_operational_planning = _render_planning
    v15._render_operational_planning_v15 = _render_planning
    ui_module.PlannerUI._v15_refinements_installed = True
