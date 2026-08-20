from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from nicegui import ui

from . import ui as ui_module
from .communication_contacts import (
    contact_directory_records,
    synchronize_known_contacts,
    update_contact,
)
from .communication_excel import (
    BATCH_SHEET,
    CONTACT_SHEET,
    MESSAGE_SHEET,
    SNAPSHOT_SHEET,
    approve_persisted_batch,
    persist_prepared_batch,
)
from .communication_queries import (
    communication_batches_for_week,
    communication_messages_for_batch,
    contacts_by_id_without_reensure,
    current_weekly_assignments,
    ensure_communication_registry_once,
    has_open_identical_batch,
    latest_communicated_snapshot_without_reensure,
)
from .domain.communication_contact_policy import partition_unavailable_recipients
from .domain.communication_planning import (
    CommunicationBatch,
    CommunicationDraft,
    build_change_notification_batch,
    build_weekly_plan_batch,
    snapshot_fingerprint,
)
from .domain.communication_review import (
    DraftReview,
    apply_manual_review,
    draft_key,
    stale_prepared_batch,
)
from .domain.communication_source import technician_ids_for_weekly_communication
from .services import week_start


COMMUNICATION_PAGE = "communications"
COMMUNICATION_SHEETS = [
    "AllocationsMO",
    "SegmentsMO",
    "DemandesMO",
    CONTACT_SHEET,
    BATCH_SHEET,
    MESSAGE_SHEET,
    SNAPSHOT_SHEET,
]


def _next_week() -> date:
    return week_start() + timedelta(days=7)


def _week_label(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _shift_week(self: ui_module.PlannerUI, delta: int) -> None:
    current = getattr(self, "_communication_week", _next_week())
    self._communication_week = current + timedelta(days=7 * delta)
    self._communication_review_fingerprint = ""
    self._communication_review_values = {}
    self.render_content.refresh()


def _reset_next_week(self: ui_module.PlannerUI) -> None:
    self._communication_week = _next_week()
    self._communication_review_fingerprint = ""
    self._communication_review_values = {}
    self.render_content.refresh()


def _contact_is_active(value: Any) -> bool:
    if value in (None, ""):
        return True
    return str(value).strip().lower() in {"oui", "true", "1", "x", "yes", "actif", "active"}


def _save_contact_from_dialog(
    self: ui_module.PlannerUI,
    person_id: str,
    display_input: Any,
    email_input: Any,
    active_input: Any,
) -> None:
    try:
        update_contact(
            self.repo,
            person_id,
            display_name=str(display_input.value or ""),
            email=str(email_input.value or ""),
            active=bool(active_input.value),
        )
        self._signature = self._signature_for_current_page()
        ui.notify("Contact enregistré.", type="positive")
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _close_contacts_dialog(self: ui_module.PlannerUI, dialog: Any) -> None:
    dialog.close()
    self._signature = self._signature_for_current_page()
    self.render_content.refresh()


def _open_contacts(self: ui_module.PlannerUI) -> None:
    try:
        ensure_communication_registry_once(self.repo)
        synchronize_known_contacts(self.repo)
        rows = contact_directory_records(self.repo)
    except Exception as exc:
        ui.notify(str(exc), type="negative")
        return

    with ui.dialog() as dialog, ui.card().classes("w-[1050px] max-w-[95vw]"):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("Répertoire de contacts").classes("text-xl font-bold")
                ui.label(
                    "Les personnes sont ajoutées automatiquement depuis les techniciens et les chargés de projet connus. "
                    "Complète seulement l'adresse courriel et ajuste le nom d'affichage au besoin."
                ).classes("text-sm muted")
            ui.space()
            ui.button(
                icon="close",
                on_click=lambda: _close_contacts_dialog(self, dialog),
            ).props("flat round")

        with ui.card().classes("w-full border border-blue-100 bg-blue-50"):
            ui.label("Clé de correspondance").classes("font-semibold text-blue-900")
            ui.label(
                "PersonneCle est synchronisée depuis le planning et demeure en lecture seule ici. "
                "L'application ne tente pas de deviner une adresse courriel à partir du nom."
            ).classes("text-sm text-blue-900")

        if not rows:
            ui.label("Aucun technicien ou chargé de projet connu.").classes("muted")
        else:
            with ui.scroll_area().classes("w-full h-[620px]"):
                with ui.column().classes("w-full gap-3 pr-2"):
                    for row in rows:
                        person_id = str(row.get("PersonneCle") or "").strip()
                        person_type = str(row.get("TypePersonne") or "").strip()
                        with ui.card().classes("w-full border"):
                            with ui.row().classes("w-full items-start gap-4"):
                                with ui.column().classes("gap-0 min-w-[220px]"):
                                    ui.label(person_id).classes("font-semibold")
                                    ui.label(person_type or "Type non précisé").classes("text-xs muted")
                                display_input = ui.input(
                                    "Nom d'affichage",
                                    value=str(row.get("NomAffiche") or person_id),
                                ).classes("min-w-[180px] flex-1")
                                email_input = ui.input(
                                    "Courriel",
                                    value=str(row.get("Courriel") or ""),
                                ).props("type=email").classes("min-w-[280px] flex-1")
                                active_input = ui.checkbox(
                                    "Actif",
                                    value=_contact_is_active(row.get("Actif")),
                                )
                                ui.button(
                                    "Enregistrer",
                                    icon="save",
                                    on_click=lambda _, key=person_id, display=display_input, email=email_input, active=active_input: _save_contact_from_dialog(
                                        self, key, display, email, active
                                    ),
                                ).props("outline no-caps")

        with ui.row().classes("w-full justify-between items-center mt-2"):
            ui.label(
                "Aucune communication n'est envoyée depuis cet écran."
            ).classes("text-xs muted")
            ui.button(
                "Fermer et actualiser",
                on_click=lambda: _close_contacts_dialog(self, dialog),
            ).props("unelevated no-caps color=primary")

    dialog.open()


def _review_state(self: ui_module.PlannerUI, batch: CommunicationBatch) -> dict[tuple[str, str], dict[str, Any]]:
    fingerprint = batch.snapshot_fingerprint
    if getattr(self, "_communication_review_fingerprint", "") != fingerprint:
        self._communication_review_fingerprint = fingerprint
        self._communication_review_values = {}
    return getattr(self, "_communication_review_values", {})


def _update_review_value(
    self: ui_module.PlannerUI,
    batch: CommunicationBatch,
    draft: CommunicationDraft,
    field: str,
    value: Any,
) -> None:
    state = _review_state(self, batch)
    key = draft_key(draft)
    current = dict(state.get(key, {}))
    current[field] = value
    state[key] = current
    self._communication_review_values = state


def _reviewed_batch(self: ui_module.PlannerUI, batch: CommunicationBatch) -> CommunicationBatch:
    state = _review_state(self, batch)
    reviews: dict[tuple[str, str], DraftReview] = {}
    for draft in batch.drafts:
        values = state.get(draft_key(draft), {})
        reviews[draft_key(draft)] = DraftReview(
            include=bool(values.get("include", True)),
            subject=values.get("subject"),
            body=values.get("body"),
        )
    return apply_manual_review(batch, reviews)


def _persist_preview(
    self: ui_module.PlannerUI,
    batch: CommunicationBatch,
    assignments: tuple[Any, ...],
    selected_week: date,
    message_kind: str,
) -> None:
    try:
        reviewed = _reviewed_batch(self, batch)
    except ValueError as exc:
        ui.notify(str(exc), type="warning")
        return
    if not reviewed.drafts:
        ui.notify("Aucun message inclus dans le lot après révision.", type="warning")
        return
    if reviewed.missing_contact_ids:
        ui.notify(
            "Complète les contacts manquants avant d'enregistrer le lot.",
            type="warning",
        )
        return
    if has_open_identical_batch(
        self.repo,
        week_start=selected_week,
        message_kind=message_kind,
        fingerprint=reviewed.snapshot_fingerprint,
    ):
        ui.notify("Un lot identique est déjà en attente de traitement.", type="warning")
        return
    batch_id = persist_prepared_batch(
        self.repo,
        reviewed,
        assignments,
        week_start=selected_week,
        message_kind=message_kind,
        prepared_by=self.repo.current_user,
    )
    ui.notify(
        f"Lot {batch_id} enregistré en statut Préparé. Aucun courriel n'a été envoyé.",
        type="positive",
        timeout=6000,
    )
    self._communication_review_fingerprint = ""
    self._communication_review_values = {}
    self._signature = self._signature_for_current_page()
    self.render_content.refresh()


def _approve_batch(self: ui_module.PlannerUI, batch_id: str, selected_week: date) -> None:
    try:
        rows = communication_batches_for_week(self.repo, selected_week)
        target = next(
            (row for row in rows if str(row.get("IDLot") or "") == str(batch_id)),
            None,
        )
        if not target:
            raise KeyError("Lot de communication introuvable.")
        current_fingerprint = snapshot_fingerprint(
            current_weekly_assignments(self.repo, selected_week)
        )
        if stale_prepared_batch(
            str(target.get("EmpreintePlanning") or ""),
            current_fingerprint,
        ):
            ui.notify(
                "Le planning a changé depuis la préparation de ce lot. Prépare un nouveau lot avant de l'approuver.",
                type="warning",
                timeout=7000,
            )
            self.render_content.refresh()
            return
        approve_persisted_batch(
            self.repo,
            batch_id,
            approved_by=self.repo.current_user,
        )
        ui.notify(
            "Lot approuvé. Aucun courriel n'a été envoyé; l'étape de transport n'est pas encore activée.",
            type="positive",
            timeout=6000,
        )
        self._signature = self._signature_for_current_page()
        self.render_content.refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _render_message_preview(
    self: ui_module.PlannerUI,
    batch: CommunicationBatch,
    draft: CommunicationDraft,
) -> None:
    state = _review_state(self, batch)
    values = state.get(draft_key(draft), {})
    include = bool(values.get("include", True))
    subject = str(values.get("subject", draft.subject))
    body = str(values.get("body", draft.body))
    audience = "Technicien" if draft.audience == "technician" else "Chargé de projet"
    with ui.expansion(f"{audience} · {draft.recipient_email}", icon="mail_outline").classes(
        "w-full border rounded"
    ):
        ui.checkbox(
            "Inclure ce destinataire dans le lot",
            value=include,
            on_change=lambda event, b=batch, d=draft: _update_review_value(
                self, b, d, "include", bool(event.value)
            ),
        )
        ui.input(
            "Objet",
            value=subject,
            on_change=lambda event, b=batch, d=draft: _update_review_value(
                self, b, d, "subject", event.value
            ),
        ).classes("w-full")
        ui.textarea(
            "Corps du message",
            value=body,
            on_change=lambda event, b=batch, d=draft: _update_review_value(
                self, b, d, "body", event.value
            ),
        ).props("autogrow").classes("w-full")


def _render_existing_message_preview(messages: list[dict[str, Any]]) -> None:
    with ui.expansion("Voir les messages préparés", icon="preview").classes("w-full"):
        for message in messages:
            with ui.card().classes("w-full border"):
                ui.label(str(message.get("Courriel") or "")).classes("text-sm font-medium")
                ui.label(str(message.get("Objet") or "")).classes("font-semibold")
                ui.textarea(
                    "Message approuvé/préparé",
                    value=str(message.get("Corps") or ""),
                ).props("readonly autogrow").classes("w-full")


def _render_existing_batches(
    self: ui_module.PlannerUI,
    selected_week: date,
    current_fingerprint: str,
) -> None:
    rows = communication_batches_for_week(self.repo, selected_week)
    with ui.card().classes("section-card w-full"):
        ui.label("File d'approbation").classes("text-lg font-semibold")
        ui.label(
            "Un lot approuvé reste sans envoi tant que l'intégration Outlook n'est pas activée."
        ).classes("text-xs muted")
        if not rows:
            ui.label("Aucun lot préparé pour cette semaine.").classes("muted")
            return
        for row in rows[:12]:
            batch_id = str(row.get("IDLot") or "")
            status = str(row.get("Statut") or "")
            kind = str(row.get("TypeCommunication") or "")
            messages = communication_messages_for_batch(self.repo, batch_id)
            stale = status == "Préparé" and stale_prepared_batch(
                str(row.get("EmpreintePlanning") or ""),
                current_fingerprint,
            )
            with ui.card().classes("w-full border"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("campaign" if kind == "planning_change" else "event_note")
                    with ui.column().classes("gap-0"):
                        ui.label(
                            "Avis de modification" if kind == "planning_change" else "Planning hebdomadaire"
                        ).classes("font-medium")
                        subtitle = f"{len(messages)} message(s) · {status}"
                        if stale:
                            subtitle += " · OBSOLÈTE"
                        ui.label(subtitle).classes(
                            "text-xs text-red-700" if stale else "text-xs muted"
                        )
                    ui.space()
                    if status == "Préparé" and not stale:
                        ui.button(
                            "Approuver ce lot",
                            icon="verified",
                            on_click=lambda _, value=batch_id, week=selected_week: _approve_batch(
                                self, value, week
                            ),
                        ).props("outline no-caps color=primary")
                    elif stale:
                        ui.label("Planning modifié — nouveau lot requis").classes(
                            "status-pill bg-red-50 text-red-700"
                        )
                    else:
                        ui.label(status).classes("status-pill bg-gray-100")
                _render_existing_message_preview(messages)


def _render_communications(self: ui_module.PlannerUI) -> None:
    try:
        ensure_communication_registry_once(self.repo)
        synchronize_known_contacts(self.repo)
        selected_week = getattr(self, "_communication_week", _next_week())
        self._communication_week = selected_week
        assignments = current_weekly_assignments(self.repo, selected_week)
        current_fingerprint = snapshot_fingerprint(assignments)
        contacts = contacts_by_id_without_reensure(self.repo)
        contact_rows = contact_directory_records(self.repo)
        inactive_contact_ids = {
            str(row.get("PersonneCle") or "").strip()
            for row in contact_rows
            if str(row.get("PersonneCle") or "").strip()
            and not _contact_is_active(row.get("Actif"))
        }
        previous_fingerprint, previous = latest_communicated_snapshot_without_reensure(
            self.repo, selected_week
        )
        technician_ids = technician_ids_for_weekly_communication(self.repo.technicians())
        manager_ids = sorted(
            {row.project_manager_id for row in assignments if row.project_manager_id}
        )

        if previous_fingerprint:
            message_kind = "planning_change"
            batch = build_change_notification_batch(
                previous,
                assignments,
                contacts,
                selected_week,
            )
        else:
            message_kind = "weekly_plan"
            batch = build_weekly_plan_batch(
                assignments,
                contacts,
                selected_week,
                technician_ids=technician_ids,
                project_manager_ids=manager_ids,
            )

        blocking_missing, inactive_suppressed = partition_unavailable_recipients(
            batch.missing_contact_ids,
            inactive_contact_ids,
        )
        batch = CommunicationBatch(
            drafts=batch.drafts,
            missing_contact_ids=blocking_missing,
            snapshot_fingerprint=batch.snapshot_fingerprint,
        )
    except Exception as exc:
        ui.label("Communications").classes("text-2xl font-bold")
        ui.label(str(exc)).classes("text-red-700")
        return

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Communications").classes("text-2xl font-bold")
            ui.label(
                "Préparer, relire et approuver les messages du planning avant toute communication."
            ).classes("muted")
        ui.space()
        ui.button(
            "Contacts",
            icon="contacts",
            on_click=lambda: _open_contacts(self),
        ).props("outline no-caps")
        ui.button(icon="chevron_left", on_click=lambda: _shift_week(self, -1)).props("flat round")
        ui.label(f"Semaine du {_week_label(selected_week)}").classes("font-semibold")
        ui.button(icon="chevron_right", on_click=lambda: _shift_week(self, 1)).props("flat round")
        ui.button("Semaine suivante", on_click=lambda: _reset_next_week(self)).props("flat no-caps")

    with ui.card().classes("w-full border border-amber-300 bg-amber-50"):
        ui.label("Contrôle manuel obligatoire").classes("font-semibold text-amber-900")
        ui.label(
            "Cet écran ne peut ni envoyer un courriel ni créer un envoi automatique. "
            "Le coordonnateur peut modifier ou exclure chaque message avant d'enregistrer le lot."
        ).classes("text-sm text-amber-900")

    with ui.grid(columns=4).classes("w-full gap-4"):
        for label, value, icon in [
            ("Attributions", len(assignments), "event_available"),
            ("Messages à relire", len(batch.drafts), "drafts"),
            ("Contacts manquants", len(batch.missing_contact_ids), "person_alert"),
            ("Planning déjà communiqué", "Oui" if previous_fingerprint else "Non", "history"),
        ]:
            with ui.card().classes("section-card w-full"):
                ui.icon(icon).classes("text-blue-700")
                ui.label(str(value)).classes("text-2xl font-bold")
                ui.label(label).classes("text-sm muted")

    if inactive_suppressed:
        with ui.card().classes("w-full border border-amber-300 bg-amber-50"):
            ui.label("Destinataires inactifs exclus du lot").classes(
                "font-semibold text-amber-900"
            )
            ui.label(", ".join(inactive_suppressed)).classes("text-sm text-amber-900")
            ui.label(
                "Ces personnes auraient normalement reçu une communication, mais leur contact est marqué inactif. "
                "Aucun courriel ne sera préparé pour elles et cet avertissement ne bloque pas le lot."
            ).classes("text-xs text-amber-900")

    if batch.missing_contact_ids:
        with ui.card().classes("w-full border border-red-200"):
            ui.label("Contacts requis avant préparation").classes("font-semibold text-red-800")
            ui.label(
                ", ".join(batch.missing_contact_ids)
            ).classes("text-sm")
            ui.label(
                "Les personnes sont déjà préremplies dans le répertoire; ajoute simplement leurs adresses courriel."
            ).classes("text-xs muted")
            ui.button(
                "Gérer les contacts",
                icon="contacts",
                on_click=lambda: _open_contacts(self),
            ).props("outline no-caps")

    with ui.card().classes("section-card w-full"):
        title = (
            "Avis de modification depuis le dernier planning communiqué"
            if previous_fingerprint
            else "Communication initiale de la semaine"
        )
        ui.label(title).classes("text-lg font-semibold")
        ui.label(
            "Chaque message ci-dessous est modifiable. Décoche un destinataire pour l'exclure du lot."
        ).classes("text-xs muted")
        if previous_fingerprint and not batch.drafts:
            ui.label("Aucun changement à communiquer depuis le dernier envoi.").classes("text-green-700")
        elif not batch.drafts:
            ui.label("Aucun message généré pour cette semaine.").classes("muted")
        else:
            for draft in batch.drafts:
                _render_message_preview(self, batch, draft)
            with ui.row().classes("w-full justify-end mt-3"):
                button = ui.button(
                    "Enregistrer le lot révisé pour approbation",
                    icon="playlist_add_check",
                    on_click=lambda _, b=batch, a=tuple(assignments), w=selected_week, k=message_kind: _persist_preview(
                        self, b, a, w, k
                    ),
                ).props("unelevated no-caps color=primary")
                if batch.missing_contact_ids:
                    button.disable()

    _render_existing_batches(self, selected_week, current_fingerprint)


def install_communication_ui() -> None:
    """Install the review-only communications page after historical UI installers."""
    if getattr(ui_module.PlannerUI, "_communication_ui_installed", False):
        return

    if not any(item[0] == COMMUNICATION_PAGE for item in ui_module.NAV_ITEMS):
        insert_at = next(
            (index for index, item in enumerate(ui_module.NAV_ITEMS) if item[0] == "data"),
            len(ui_module.NAV_ITEMS),
        )
        ui_module.NAV_ITEMS.insert(
            insert_at,
            (COMMUNICATION_PAGE, "outgoing_mail", "Communications"),
        )

    original_render_content = ui_module.PlannerUI._render_content
    original_page_sheets = ui_module.PlannerUI._page_sheets

    def render_content(self: ui_module.PlannerUI) -> None:
        if self.current_page == COMMUNICATION_PAGE:
            _render_communications(self)
            return
        original_render_content(self)

    def page_sheets(self: ui_module.PlannerUI) -> list[str]:
        if self.current_page == COMMUNICATION_PAGE:
            return COMMUNICATION_SHEETS
        return original_page_sheets(self)

    ui_module.PlannerUI._render_content = render_content
    ui_module.PlannerUI._page_sheets = page_sheets
    ui_module.PlannerUI._communication_ui_installed = True
