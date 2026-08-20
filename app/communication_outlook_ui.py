from __future__ import annotations

from datetime import date

from nicegui import ui

from . import communication_ui
from .communication_excel import (
    mark_persisted_batch_communicated,
    mark_stale_open_batches_obsolete,
)
from .communication_queries import (
    communication_batches_for_week,
    communication_messages_for_batch,
    current_weekly_assignments,
)
from .communication_transport_excel import (
    mark_persisted_draft_batch_obsolete,
    mark_persisted_message_drafts_created,
)
from .domain.communication_audit import STATUS_APPROVED, STATUS_DRAFTS_CREATED
from .domain.communication_planning import snapshot_fingerprint
from .domain.communication_transport import (
    all_message_drafts_created,
    draft_created_message_ids,
    pending_draft_message_ids,
)
from .outlook_drafts import (
    OutlookDraftRequest,
    OutlookDraftTransportError,
    create_outlook_drafts,
)


def _batch_for_week(self, batch_id: str, selected_week: date):
    return next(
        (
            row
            for row in communication_batches_for_week(self.repo, selected_week)
            if str(row.get("IDLot") or "") == str(batch_id)
        ),
        None,
    )


def _current_fingerprint(self, selected_week: date) -> str:
    return snapshot_fingerprint(current_weekly_assignments(self.repo, selected_week))


def _create_batch_drafts(self, batch_id: str, selected_week: date) -> None:
    try:
        current_fingerprint = _current_fingerprint(self, selected_week)
        mark_stale_open_batches_obsolete(
            self.repo,
            selected_week,
            current_fingerprint,
        )
        batch = _batch_for_week(self, batch_id, selected_week)
        if not batch or str(batch.get("Statut") or "") != STATUS_APPROVED:
            ui.notify(
                "Ce lot n'est plus approuvé pour le planning courant. Actualise la communication avant de créer des brouillons.",
                type="warning",
                timeout=7000,
            )
            self.render_content.refresh()
            return

        messages = communication_messages_for_batch(self.repo, batch_id)
        pending_ids = set(pending_draft_message_ids(messages))
        if not pending_ids:
            if all_message_drafts_created(messages):
                mark_persisted_message_drafts_created(self.repo, batch_id, ())
                ui.notify("Tous les brouillons Outlook étaient déjà créés.", type="positive")
                self.render_content.refresh()
                return
            ui.notify("Aucun message approuvé à convertir en brouillon Outlook.", type="warning")
            return

        requests = [
            OutlookDraftRequest(
                message_id=str(row.get("IDMessage") or ""),
                batch_id=batch_id,
                to_address=str(row.get("Courriel") or ""),
                subject=str(row.get("Objet") or ""),
                body=str(row.get("Corps") or ""),
            )
            for row in messages
            if str(row.get("IDMessage") or "") in pending_ids
        ]
        result = create_outlook_drafts(requests)
        completed = result.completed_message_ids
        if completed:
            _, total, complete = mark_persisted_message_drafts_created(
                self.repo,
                batch_id,
                completed,
            )
        else:
            total = len(messages)
            complete = False

        created_count = len(result.created_message_ids)
        reused_count = len(result.existing_message_ids)
        failure_count = len(result.failures)
        if complete:
            ui.notify(
                f"{total} brouillon(s) sont prêts dans Outlook. Aucun courriel n'a été envoyé.",
                type="positive",
                timeout=7000,
            )
        elif completed:
            ui.notify(
                f"Brouillons Outlook : {created_count} créé(s), {reused_count} déjà existant(s), {failure_count} échec(s). "
                "Aucun courriel n'a été envoyé.",
                type="warning" if failure_count else "positive",
                timeout=8000,
            )
        elif failure_count:
            ui.notify(
                "Aucun brouillon Outlook n'a pu être créé. Aucun courriel n'a été envoyé.",
                type="negative",
                timeout=8000,
            )
        self._signature = self._signature_for_current_page()
        self.render_content.refresh()
    except OutlookDraftTransportError as exc:
        ui.notify(str(exc), type="negative", timeout=9000)
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)


def _communicate_batch(self, dialog, batch_id: str, selected_week: date) -> None:
    try:
        batch = _batch_for_week(self, batch_id, selected_week)
        if not batch or str(batch.get("Statut") or "") != STATUS_DRAFTS_CREATED:
            raise ValueError("Ce lot n'est plus en attente de confirmation d'envoi.")
        messages = communication_messages_for_batch(self.repo, batch_id)
        if not all_message_drafts_created(messages):
            raise ValueError("Tous les brouillons Outlook doivent être créés avant cette confirmation.")
        mark_persisted_batch_communicated(self.repo, batch_id)
        dialog.close()
        ui.notify(
            "Lot marqué Communiqué. Cette version devient la référence pour les prochains avis de modification.",
            type="positive",
            timeout=7000,
        )
        self._signature = self._signature_for_current_page()
        self.render_content.refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)


def _confirm_communicated_dialog(
    self,
    batch_id: str,
    selected_week: date,
    *,
    planning_changed: bool,
) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[650px] max-w-[95vw]"):
        ui.label("Confirmer l'envoi manuel").classes("text-xl font-bold")
        ui.label(
            "Cette action n'envoie aucun courriel. Elle doit être utilisée seulement après avoir envoyé manuellement tous les brouillons depuis Outlook."
        ).classes("text-sm")
        if planning_changed:
            with ui.card().classes("w-full border border-amber-300 bg-amber-50"):
                ui.label("Le planning a changé depuis la création de ces brouillons.").classes(
                    "font-semibold text-amber-900"
                )
                ui.label(
                    "Si les courriels ont déjà été envoyés, confirme l'envoi : l'application conservera cette ancienne version comme communiquée et préparera ensuite les avis correctifs nécessaires."
                ).classes("text-sm text-amber-900")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button(
                "Oui, tous les courriels ont été envoyés",
                icon="mark_email_read",
                on_click=lambda: _communicate_batch(
                    self, dialog, batch_id, selected_week
                ),
            ).props("unelevated no-caps color=primary")
    dialog.open()


def _obsolete_unsent_drafts(self, dialog, batch_id: str) -> None:
    try:
        mark_persisted_draft_batch_obsolete(self.repo, batch_id)
        dialog.close()
        ui.notify(
            "Lot rendu obsolète. Supprime manuellement dans Outlook les brouillons correspondants s'ils sont encore présents.",
            type="warning",
            timeout=8000,
        )
        self._signature = self._signature_for_current_page()
        self.render_content.refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)


def _obsolete_drafts_dialog(self, batch_id: str) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[650px] max-w-[95vw]"):
        ui.label("Abandonner ces brouillons").classes("text-xl font-bold")
        ui.label(
            "L'application marquera ce lot Obsolète, mais ne supprimera aucun brouillon dans Outlook. "
            "Utilise cette action seulement si ces courriels n'ont pas été envoyés, puis supprime les anciens brouillons dans Outlook."
        ).classes("text-sm")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button(
                "Rendre le lot obsolète",
                icon="block",
                on_click=lambda: _obsolete_unsent_drafts(self, dialog, batch_id),
            ).props("unelevated no-caps color=negative")
    dialog.open()


def _render_outlook_actions(self, selected_week: date, current_fingerprint: str) -> None:
    rows = communication_batches_for_week(self.repo, selected_week)
    actionable = [
        row
        for row in rows
        if str(row.get("Statut") or "") in {STATUS_APPROVED, STATUS_DRAFTS_CREATED}
    ]

    with ui.card().classes("section-card w-full"):
        ui.label("Outlook — envoi manuel").classes("text-lg font-semibold")
        ui.label(
            "L'application peut uniquement créer des brouillons dans Outlook. Elle ne contient aucune action d'envoi automatique."
        ).classes("text-xs muted")
        ui.label(
            "La création utilise une installation Outlook pour Windows compatible avec l'automatisation COM, généralement Outlook classique."
        ).classes("text-xs muted")

        if not actionable:
            ui.label("Aucun lot approuvé en attente d'action Outlook.").classes("muted")
            return

        for row in actionable[:6]:
            batch_id = str(row.get("IDLot") or "")
            status = str(row.get("Statut") or "")
            messages = communication_messages_for_batch(self.repo, batch_id)
            pending = pending_draft_message_ids(messages)
            created = draft_created_message_ids(messages)
            total = len(messages)
            changed = str(row.get("EmpreintePlanning") or "") != current_fingerprint

            with ui.card().classes("w-full border"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("mail_outline")
                    with ui.column().classes("gap-0"):
                        ui.label(
                            "Avis de modification"
                            if str(row.get("TypeCommunication") or "") == "planning_change"
                            else "Planning hebdomadaire"
                        ).classes("font-medium")
                        ui.label(
                            f"{len(created)}/{total} brouillon(s) créé(s) · {status}"
                        ).classes("text-xs muted")
                    ui.space()
                    if status == STATUS_APPROVED:
                        ui.button(
                            f"Créer les brouillons Outlook ({len(pending)})",
                            icon="drafts",
                            on_click=lambda _, value=batch_id, week=selected_week: _create_batch_drafts(
                                self, value, week
                            ),
                        ).props("unelevated no-caps color=primary")
                    elif status == STATUS_DRAFTS_CREATED and not changed:
                        ui.button(
                            "Confirmer l'envoi manuel",
                            icon="mark_email_read",
                            on_click=lambda _, value=batch_id, week=selected_week: _confirm_communicated_dialog(
                                self, value, week, planning_changed=False
                            ),
                        ).props("outline no-caps color=primary")

                if status == STATUS_DRAFTS_CREATED:
                    ui.label(
                        "Les messages sont seulement enregistrés dans le dossier Brouillons d'Outlook. Ouvre Outlook, relis-les au besoin et envoie-les manuellement."
                    ).classes("text-sm")

                if status == STATUS_DRAFTS_CREATED and changed:
                    with ui.card().classes("w-full border border-amber-300 bg-amber-50"):
                        ui.label(
                            "Le planning a changé depuis la création des brouillons."
                        ).classes("font-semibold text-amber-900")
                        ui.label(
                            "S'ils ont déjà été envoyés, confirme l'envoi afin que cette version devienne la référence et que les avis correctifs soient générés. "
                            "S'ils n'ont pas été envoyés, rends plutôt ce lot obsolète et supprime les anciens brouillons dans Outlook."
                        ).classes("text-sm text-amber-900")
                        with ui.row().classes("w-full gap-2"):
                            ui.button(
                                "Ils ont déjà été envoyés",
                                icon="mark_email_read",
                                on_click=lambda _, value=batch_id, week=selected_week: _confirm_communicated_dialog(
                                    self, value, week, planning_changed=True
                                ),
                            ).props("outline no-caps color=primary")
                            ui.button(
                                "Ils n'ont pas été envoyés",
                                icon="block",
                                on_click=lambda _, value=batch_id: _obsolete_drafts_dialog(
                                    self, value
                                ),
                            ).props("outline no-caps color=negative")


def install_communication_outlook_ui() -> None:
    """Add explicit Outlook Drafts actions after the existing communication review UI."""
    if getattr(communication_ui, "_communication_outlook_ui_installed", False):
        return

    original_render = communication_ui._render_communications

    def render_communications(self) -> None:
        original_render(self)
        selected_week = getattr(
            self,
            "_communication_week",
            communication_ui._next_week(),
        )
        try:
            current_fingerprint = _current_fingerprint(self, selected_week)
            _render_outlook_actions(self, selected_week, current_fingerprint)
        except Exception as exc:
            with ui.card().classes("section-card w-full border border-red-200"):
                ui.label("Outlook — envoi manuel").classes("text-lg font-semibold")
                ui.label(str(exc)).classes("text-red-700")

    communication_ui._render_communications = render_communications
    communication_ui._communication_outlook_ui_installed = True
