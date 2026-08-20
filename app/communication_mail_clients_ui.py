from __future__ import annotations

from datetime import date

from nicegui import ui

from . import communication_outlook_ui, communication_ui
from .communication_excel import (
    approve_persisted_batch,
    mark_persisted_batch_communicated,
    mark_stale_open_batches_obsolete,
)
from .communication_mail_preferences import (
    MAIL_CLIENT_OUTLOOK,
    MAIL_CLIENT_THUNDERBIRD,
    mail_client_preference,
    set_mail_client_preference,
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
from .domain.communication_audit import (
    STATUS_APPROVED,
    STATUS_DRAFTS_CREATED,
    STATUS_OBSOLETE,
    STATUS_PREPARED,
)
from .domain.communication_planning import snapshot_fingerprint
from .domain.communication_transport import (
    all_message_drafts_created,
    draft_created_message_ids,
    pending_draft_message_ids,
)
from .thunderbird_bridge import (
    ThunderbirdDraftRequest,
    discard_thunderbird_batch,
    open_thunderbird_integration_folder,
    prepare_thunderbird_integration,
    queue_thunderbird_drafts,
    thunderbird_batch_status,
    thunderbird_created_message_ids,
)


CLIENT_LABELS = {
    MAIL_CLIENT_OUTLOOK: "Outlook classique",
    MAIL_CLIENT_THUNDERBIRD: "Thunderbird",
}


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


def _client(self) -> str:
    return mail_client_preference(self.repo)


def _set_client(self, value: str) -> None:
    try:
        set_mail_client_preference(self.repo, str(value or ""))
        self.render_content.refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _approve_batch(self, batch_id: str, selected_week: date) -> None:
    try:
        current_fingerprint = _current_fingerprint(self, selected_week)
        mark_stale_open_batches_obsolete(self.repo, selected_week, current_fingerprint)
        batch = _batch_for_week(self, batch_id, selected_week)
        if not batch or str(batch.get("Statut") or "") != STATUS_PREPARED:
            ui.notify(
                "Ce lot ne peut plus être approuvé pour le planning courant.",
                type="warning",
                timeout=7000,
            )
            self.render_content.refresh()
            return
        approve_persisted_batch(self.repo, batch_id, approved_by=self.repo.current_user)
        label = CLIENT_LABELS.get(_client(self), "client courriel")
        ui.notify(
            f"Lot approuvé. Aucun courriel n'a été envoyé. Tu peux maintenant préparer les brouillons dans {label}.",
            type="positive",
            timeout=7000,
        )
        self._signature = self._signature_for_current_page()
        self.render_content.refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)


def _thunderbird_requests(self, batch_id: str) -> list[ThunderbirdDraftRequest]:
    messages = communication_messages_for_batch(self.repo, batch_id)
    pending_ids = set(pending_draft_message_ids(messages))
    return [
        ThunderbirdDraftRequest(
            message_id=str(row.get("IDMessage") or ""),
            batch_id=batch_id,
            to_address=str(row.get("Courriel") or ""),
            subject=str(row.get("Objet") or ""),
            body=str(row.get("Corps") or ""),
        )
        for row in messages
        if str(row.get("IDMessage") or "") in pending_ids
    ]


def _queue_thunderbird_batch(self, batch_id: str, selected_week: date) -> None:
    try:
        current_fingerprint = _current_fingerprint(self, selected_week)
        mark_stale_open_batches_obsolete(self.repo, selected_week, current_fingerprint)
        batch = _batch_for_week(self, batch_id, selected_week)
        if not batch or str(batch.get("Statut") or "") != STATUS_APPROVED:
            ui.notify(
                "Ce lot n'est plus approuvé pour le planning courant.",
                type="warning",
                timeout=7000,
            )
            self.render_content.refresh()
            return
        requests = _thunderbird_requests(self, batch_id)
        if not requests:
            ui.notify("Aucun message approuvé à préparer dans Thunderbird.", type="warning")
            return
        queued = queue_thunderbird_drafts(requests)
        status = thunderbird_batch_status(batch_id)
        if queued:
            message = (
                f"{queued} message(s) remis au pont Thunderbird. Laisse Thunderbird ouvert quelques secondes, "
                "puis clique « Vérifier les brouillons Thunderbird »."
            )
            if not status.extension_seen_recently:
                message += " Le pont Thunderbird n'est pas encore détecté; utilise « Configurer Thunderbird » au besoin."
            ui.notify(message, type="positive", timeout=9000)
        else:
            ui.notify(
                "Ces messages sont déjà indiqués comme créés par le pont Thunderbird. Utilise « Vérifier » pour synchroniser le lot.",
                type="info",
                timeout=8000,
            )
        self.render_content.refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)


def _verify_thunderbird_batch(self, batch_id: str) -> None:
    try:
        created_ids = thunderbird_created_message_ids(batch_id)
        status = thunderbird_batch_status(batch_id)
        if created_ids:
            _, total, complete = mark_persisted_message_drafts_created(
                self.repo, batch_id, created_ids
            )
        else:
            messages = communication_messages_for_batch(self.repo, batch_id)
            total = len(messages)
            complete = all_message_drafts_created(messages)

        if complete:
            discard_thunderbird_batch(batch_id)
            ui.notify(
                f"{total} brouillon(s) sont prêts dans Thunderbird. Aucun courriel n'a été envoyé.",
                type="positive",
                timeout=7000,
            )
        elif status.failed:
            ui.notify(
                f"Thunderbird : {status.created}/{status.total} brouillon(s) créé(s), {status.failed} échec(s). "
                "Tu peux relancer la préparation pour réessayer les échecs.",
                type="warning",
                timeout=9000,
            )
        elif status.total:
            ui.notify(
                f"Thunderbird traite encore le lot : {status.created}/{status.total} brouillon(s) prêt(s).",
                type="info",
                timeout=7000,
            )
        else:
            ui.notify(
                "Aucune demande Thunderbird n'est en attente pour ce lot. Prépare d'abord les brouillons.",
                type="warning",
            )
        self._signature = self._signature_for_current_page()
        self.render_content.refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)


def _thunderbird_setup_dialog(self) -> None:
    try:
        prepare_thunderbird_integration()
        open_thunderbird_integration_folder()
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)
        return

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-[95vw]"):
        ui.label("Configurer Thunderbird").classes("text-xl font-bold")
        ui.label(
            "Le pont natif RessourcePlanner est enregistré pour ton compte Windows et le fichier d'extension XPI a été créé."
        ).classes("text-sm")
        with ui.card().classes("w-full border border-blue-200 bg-blue-50"):
            ui.label("Installation unique dans Thunderbird").classes("font-semibold text-blue-900")
            ui.label(
                "Dans Thunderbird : Modules complémentaires et thèmes → bouton engrenage → Installer un module depuis un fichier. "
                "Choisis RessourcePlanner-Thunderbird-Draft-Bridge.xpi dans le dossier qui vient de s'ouvrir, puis redémarre Thunderbird."
            ).classes("text-sm text-blue-900")
        ui.label(
            "L'extension demande seulement les permissions nécessaires pour créer et enregistrer des brouillons et communiquer avec le pont local. "
            "Elle ne demande pas la permission compose.send."
        ).classes("text-xs muted")
        with ui.row().classes("w-full justify-end"):
            ui.button("Fermer", on_click=dialog.close).props("unelevated no-caps color=primary")
    dialog.open()


def _communicate_batch(self, dialog, batch_id: str, selected_week: date) -> None:
    try:
        batch = _batch_for_week(self, batch_id, selected_week)
        if not batch or str(batch.get("Statut") or "") != STATUS_DRAFTS_CREATED:
            raise ValueError("Ce lot n'est plus en attente de confirmation d'envoi.")
        messages = communication_messages_for_batch(self.repo, batch_id)
        if not all_message_drafts_created(messages):
            raise ValueError("Tous les brouillons doivent être créés avant cette confirmation.")
        mark_persisted_batch_communicated(self.repo, batch_id)
        discard_thunderbird_batch(batch_id)
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


def _confirm_communicated_dialog(self, batch_id: str, selected_week: date, *, planning_changed: bool) -> None:
    client = _client(self)
    label = CLIENT_LABELS.get(client, "ton client courriel")
    with ui.dialog() as dialog, ui.card().classes("w-[650px] max-w-[95vw]"):
        ui.label("Confirmer l'envoi manuel").classes("text-xl font-bold")
        ui.label(
            f"Cette action n'envoie aucun courriel. Utilise-la seulement après avoir envoyé manuellement tous les brouillons depuis {label}."
        ).classes("text-sm")
        if planning_changed:
            with ui.card().classes("w-full border border-amber-300 bg-amber-50"):
                ui.label("Le planning a changé depuis la création de ces brouillons.").classes(
                    "font-semibold text-amber-900"
                )
                ui.label(
                    "S'ils ont déjà été envoyés, confirme l'envoi : cette ancienne version sera conservée comme communiquée et les prochains avis corrigeront les changements."
                ).classes("text-sm text-amber-900")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button(
                "Oui, tous les courriels ont été envoyés",
                icon="mark_email_read",
                on_click=lambda: _communicate_batch(self, dialog, batch_id, selected_week),
            ).props("unelevated no-caps color=primary")
    dialog.open()


def _obsolete_unsent_drafts(self, dialog, batch_id: str) -> None:
    try:
        client = _client(self)
        label = CLIENT_LABELS.get(client, "le client courriel")
        mark_persisted_draft_batch_obsolete(self.repo, batch_id)
        discard_thunderbird_batch(batch_id)
        dialog.close()
        ui.notify(
            f"Lot rendu obsolète. Supprime manuellement dans {label} les brouillons correspondants s'ils sont encore présents.",
            type="warning",
            timeout=8000,
        )
        self._signature = self._signature_for_current_page()
        self.render_content.refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)


def _obsolete_drafts_dialog(self, batch_id: str) -> None:
    label = CLIENT_LABELS.get(_client(self), "le client courriel")
    with ui.dialog() as dialog, ui.card().classes("w-[650px] max-w-[95vw]"):
        ui.label("Abandonner ces brouillons").classes("text-xl font-bold")
        ui.label(
            f"L'application marquera ce lot Obsolète, mais ne supprimera aucun brouillon dans {label}. "
            "Utilise cette action seulement si ces courriels n'ont pas été envoyés."
        ).classes("text-sm")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button(
                "Rendre le lot obsolète",
                icon="block",
                on_click=lambda: _obsolete_unsent_drafts(self, dialog, batch_id),
            ).props("unelevated no-caps color=negative")
    dialog.open()


def _render_existing_batches(self, selected_week: date, current_fingerprint: str) -> None:
    rows = communication_batches_for_week(self.repo, selected_week)
    with ui.card().classes("section-card w-full"):
        ui.label("File d'approbation").classes("text-lg font-semibold")
        ui.label(
            "L'approbation ne transmet rien. Un lot approuvé peut ensuite créer des brouillons dans le client courriel choisi."
        ).classes("text-xs muted")
        if not rows:
            ui.label("Aucun lot préparé pour cette semaine.").classes("muted")
            return
        for row in rows[:12]:
            batch_id = str(row.get("IDLot") or "")
            status = str(row.get("Statut") or "")
            kind = str(row.get("TypeCommunication") or "")
            messages = communication_messages_for_batch(self.repo, batch_id)
            stale = (
                status in {STATUS_PREPARED, STATUS_APPROVED}
                and str(row.get("EmpreintePlanning") or "") != current_fingerprint
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
                        ui.label(subtitle).classes("text-xs text-red-700" if stale else "text-xs muted")
                    ui.space()
                    if status == STATUS_PREPARED and not stale:
                        ui.button(
                            "Approuver ce lot",
                            icon="verified",
                            on_click=lambda _, value=batch_id, week=selected_week: _approve_batch(self, value, week),
                        ).props("outline no-caps color=primary")
                    elif stale or status == STATUS_OBSOLETE:
                        ui.label("Planning modifié — lot obsolète").classes("status-pill bg-red-50 text-red-700")
                    else:
                        ui.label(status).classes("status-pill bg-gray-100")
                communication_ui._render_existing_message_preview(messages)


def _render_mail_actions(self, selected_week: date, current_fingerprint: str) -> None:
    client = _client(self)
    rows = communication_batches_for_week(self.repo, selected_week)
    actionable = [
        row for row in rows if str(row.get("Statut") or "") in {STATUS_APPROVED, STATUS_DRAFTS_CREATED}
    ]

    with ui.card().classes("section-card w-full"):
        with ui.row().classes("w-full items-center gap-3"):
            with ui.column().classes("gap-0"):
                ui.label("Client courriel — envoi manuel").classes("text-lg font-semibold")
                ui.label(
                    "RessourcePlanner prépare seulement des brouillons. L'envoi reste une action manuelle dans le client courriel."
                ).classes("text-xs muted")
            ui.space()
            ui.toggle(
                {MAIL_CLIENT_OUTLOOK: "Outlook classique", MAIL_CLIENT_THUNDERBIRD: "Thunderbird"},
                value=client,
                on_change=lambda event: _set_client(self, event.value),
            ).props("no-caps")

        if client == MAIL_CLIENT_THUNDERBIRD:
            recent = any(thunderbird_batch_status(str(row.get("IDLot") or "")).extension_seen_recently for row in actionable)
            with ui.card().classes(
                "w-full border border-green-200 bg-green-50" if recent else "w-full border border-amber-200 bg-amber-50"
            ):
                with ui.row().classes("w-full items-center"):
                    ui.icon("check_circle" if recent else "extension")
                    ui.label(
                        "Pont Thunderbird détecté" if recent else "Pont Thunderbird non détecté récemment"
                    ).classes("font-semibold")
                    ui.space()
                    ui.button(
                        "Configurer Thunderbird",
                        icon="settings",
                        on_click=lambda: _thunderbird_setup_dialog(self),
                    ).props("outline no-caps")
                ui.label(
                    "L'intégration utilise une petite extension Thunderbird locale. Elle possède compose.save, mais aucune permission compose.send."
                ).classes("text-xs")
        else:
            ui.label(
                "Outlook classique est automatisé localement par COM et les messages sont enregistrés dans Brouillons."
            ).classes("text-xs muted")

        if not actionable:
            ui.label("Aucun lot approuvé en attente d'action courriel.").classes("muted")
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
                        ui.label(f"{len(created)}/{total} brouillon(s) synchronisé(s) · {status}").classes("text-xs muted")
                    ui.space()
                    if status == STATUS_APPROVED and client == MAIL_CLIENT_OUTLOOK:
                        ui.button(
                            f"Créer les brouillons Outlook ({len(pending)})",
                            icon="drafts",
                            on_click=lambda _, value=batch_id, week=selected_week: communication_outlook_ui._create_batch_drafts(
                                self, value, week
                            ),
                        ).props("unelevated no-caps color=primary")
                    elif status == STATUS_APPROVED and client == MAIL_CLIENT_THUNDERBIRD:
                        bridge = thunderbird_batch_status(batch_id)
                        if bridge.total:
                            ui.button(
                                "Vérifier les brouillons Thunderbird",
                                icon="sync",
                                on_click=lambda _, value=batch_id: _verify_thunderbird_batch(self, value),
                            ).props("outline no-caps color=primary")
                        ui.button(
                            f"Préparer dans Thunderbird ({len(pending)})",
                            icon="drafts",
                            on_click=lambda _, value=batch_id, week=selected_week: _queue_thunderbird_batch(
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

                if status == STATUS_APPROVED and client == MAIL_CLIENT_THUNDERBIRD:
                    bridge = thunderbird_batch_status(batch_id)
                    if bridge.total:
                        ui.label(
                            f"Pont Thunderbird : {bridge.created}/{bridge.total} créé(s), {bridge.pending} en attente, {bridge.failed} échec(s)."
                        ).classes("text-sm")

                if status == STATUS_DRAFTS_CREATED:
                    label = CLIENT_LABELS.get(client, "ton client courriel")
                    ui.label(
                        f"Les messages sont seulement enregistrés comme brouillons dans {label}. Relis-les et envoie-les manuellement."
                    ).classes("text-sm")

                if status == STATUS_DRAFTS_CREATED and changed:
                    with ui.card().classes("w-full border border-amber-300 bg-amber-50"):
                        ui.label("Le planning a changé depuis la création des brouillons.").classes("font-semibold text-amber-900")
                        ui.label(
                            "S'ils ont déjà été envoyés, confirme l'envoi pour conserver cette version comme référence. "
                            "Sinon, rends ce lot obsolète et supprime les anciens brouillons dans le client courriel."
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
                                on_click=lambda _, value=batch_id: _obsolete_drafts_dialog(self, value),
                            ).props("outline no-caps color=negative")


def install_communication_mail_clients_ui() -> None:
    """Upgrade the transitional Outlook transport UI to a local multi-client draft workflow."""
    if getattr(communication_ui, "_communication_mail_clients_ui_installed", False):
        return

    communication_ui._approve_batch = _approve_batch
    communication_ui._render_existing_batches = _render_existing_batches
    communication_outlook_ui._approve_batch_with_outlook = _approve_batch
    communication_outlook_ui._render_existing_batches_with_outlook = _render_existing_batches
    communication_outlook_ui._render_outlook_actions = _render_mail_actions
    communication_outlook_ui._confirm_communicated_dialog = _confirm_communicated_dialog
    communication_outlook_ui._obsolete_drafts_dialog = _obsolete_drafts_dialog
    communication_ui._communication_mail_clients_ui_installed = True
