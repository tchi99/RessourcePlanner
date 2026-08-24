from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from nicegui import ui

from .config import save_workbook_path
from .demand_requests_page import DemandRequestsPage
from .operational_planning_page import OperationalPlanningPage
from .segment_repository import SEGMENT_SHEET
from .segments_page import SegmentsPage
from .excel_repository import EFFORT_STATUSES, ExcelRepository, MASTER_SHEETS
from .services import (
    active_efforts_for_week,
    effort_overlaps_day,
    week_days,
    week_start,
    weekly_load,
)


NAV_ITEMS = [
    ("dashboard", "dashboard", "Tableau de bord"),
    ("planning", "calendar_month", "Planification"),
    ("segments", "view_timeline", "Segments"),
    ("requests", "approval", "Demandes / approbations"),
    ("data", "table_view", "Données Excel"),
    ("settings", "settings", "Paramètres"),
]

PASTEL_CLASSES = [
    "shift-blue",
    "shift-yellow",
    "shift-purple",
    "shift-green",
    "shift-pink",
]


class PlannerUI:
    def __init__(
        self,
        repo: ExcelRepository,
        refresh_seconds: float = 3.0,
    ):
        self.repo = repo
        self.refresh_seconds = refresh_seconds
        self.current_page = "dashboard" if repo.is_configured else "settings"
        self.current_week = week_start()
        self.selected_request: str | None = None
        self.selected_sheet = "Liste_Effort"
        self.interaction_lock = False
        self._signature: str | None = None

        # La page Demandes possède désormais son propre rendu et ses actions.
        self.demand_requests_page = DemandRequestsPage(self)
        self.segments_page = SegmentsPage(self)
        planning_renderer = getattr(type(self), "_operational_planning_renderer", None)
        if not callable(planning_renderer):
            planning_renderer = type(self).render_planning
        self.operational_planning_page = OperationalPlanningPage(
            self, planning_renderer
        )

        # Refreshable principal conservé sur le shell historique pendant l'extraction
        # progressive des autres pages. L'alias request_actions protège les adaptateurs
        # encore susceptibles de rafraîchir la sélection sans réintroduire de méthode UI.
        self.render_content = ui.refreshable(
            self._render_content
        )
        self.request_actions = self.demand_requests_page.request_actions

        self._setup_style()

    def _setup_style(self) -> None:
        ui.add_head_html(
            """
            <style>
              body { background:#f5f7fb; color:#1f2937; }
              .app-title { font-weight:700; letter-spacing:.2px; }
              .nav-button { width:100%; justify-content:flex-start; border-radius:8px; }
              .kpi-card { min-height:118px; border:1px solid #e5e7eb; box-shadow:0 1px 2px rgba(0,0,0,.04); }
              .kpi-value { font-size:2rem; line-height:1; font-weight:700; }
              .section-card { border:1px solid #e5e7eb; box-shadow:0 1px 2px rgba(0,0,0,.03); }
              .schedule-grid { width:100%; min-width:1180px; }
              .day-header { min-height:68px; background:#f8fafc; border:1px solid #e5e7eb; }
              .resource-cell { min-height:105px; background:white; border:1px solid #e5e7eb; }
              .day-cell { min-height:105px; background:white; border:1px solid #e5e7eb; padding:5px; }
              .weekend-cell { background:#fafafa; }
              .shift-card { width:100%; border-radius:6px; padding:7px 8px; text-align:left; cursor:pointer; margin-bottom:4px; border-left:4px solid rgba(0,0,0,.25); }
              .shift-card:hover { filter:brightness(.98); box-shadow:0 1px 4px rgba(0,0,0,.12); }
              .shift-blue { background:#dff1fb; border-left-color:#1989b8; }
              .shift-yellow { background:#fff1bd; border-left-color:#d49a00; }
              .shift-purple { background:#efd7ef; border-left-color:#8d3e93; }
              .shift-green { background:#dcf3df; border-left-color:#3a8c46; }
              .shift-pink { background:#f8dede; border-left-color:#b95b5b; }
              .muted { color:#6b7280; }
              .status-pill { border-radius:999px; padding:2px 8px; font-size:.78rem; font-weight:600; }
              .sync-ok { color:#2e7d32; }
              .sync-bad { color:#c62828; }
            </style>
            """
        )

    def build(self) -> None:
        connection_error = None
        if self.repo.is_configured:
            try:
                self.repo.connect()
            except Exception as exc:
                connection_error = str(exc)
                self.current_page = "settings"
        else:
            connection_error = "Aucun fichier Excel n'est encore configuré."

        self._signature = self._signature_for_current_page()

        with ui.header(elevated=True).classes(
            "items-center bg-white text-gray-800"
        ):
            ui.icon("calendar_month", size="28px").classes("text-blue-700")
            ui.label("Planification MO — V1.1").classes("app-title text-lg")
            ui.space()
            self.sync_label = ui.label(
                "Excel connecté" if self.repo.is_connected else "Excel non connecté"
            ).classes("sync-ok text-sm" if self.repo.is_connected else "sync-bad text-sm")
            ui.button(icon="refresh", on_click=self.manual_refresh).props("flat round").tooltip(
                "Rafraîchir depuis Excel"
            )

        with ui.left_drawer(value=True).classes("bg-slate-900 text-white"):
            ui.label("PLANIFICATION").classes("text-xs opacity-60 px-2 mt-3 mb-2")
            for key, icon, label in NAV_ITEMS:
                ui.button(
                    label, icon=icon, on_click=lambda _, page=key: self.navigate(page)
                ).props("flat no-caps").classes("nav-button text-white")

            ui.separator().classes("opacity-20 my-4")
            ui.label("Source de données").classes("text-xs opacity-60 px-2")
            self.source_label = ui.label(self._source_text()).classes("text-sm px-2 break-all")
            ui.label(f"Utilisateur : {self.repo.current_user}").classes(
                "text-xs opacity-60 px-2 mt-2"
            )

        with ui.column().classes("w-full p-5 gap-4"):
            if connection_error:
                ui.notify(connection_error, type="warning", timeout=5000)
            self.render_content()

        ui.timer(self.refresh_seconds, self.auto_refresh)

    def navigate(self, page: str) -> None:
        if page != "settings" and not self.repo.is_connected:
            try:
                self.repo.connect()
            except Exception as exc:
                self.current_page = "settings"
                ui.notify(str(exc), type="warning")
                self.render_content.refresh()
                return
        self.current_page = page
        self.selected_request = None
        self._signature = self._signature_for_current_page()
        self.render_content.refresh()

    def _page_sheets(self) -> list[str]:
        if self.current_page == "settings" or not self.repo.is_connected:
            return []
        if self.current_page == "planning":
            return [
                "Liste_Effort",
                "Configuration des listes",
                "DemandesMO",
            ]
        if self.current_page == "requests":
            return [
                "DemandesMO",
                "Historique",
                "Liste des projets",
            ]
        if self.current_page == "segments":
            return [SEGMENT_SHEET, "DemandesMO", "Disponibilites", "Liste_Effort"]
        if self.current_page == "data":
            return [self.selected_sheet]
        return [
            "Liste_Effort",
            "Configuration des listes",
            "DemandesMO",
        ]

    def _signature_for_current_page(self) -> str:
        if not self.repo.is_connected:
            return "not-connected"
        try:
            return self.repo.signature(self._page_sheets())
        except Exception:
            return "error"

    async def auto_refresh(self) -> None:
        if self.interaction_lock or not self.repo.is_connected:
            return
        try:
            signature = (
                self._signature_for_current_page()
            )
            self.sync_label.text = "Excel connecté"
            self.sync_label.classes(
                remove="sync-bad", add="sync-ok"
            )
            if self._signature is None:
                self._signature = signature
            elif signature != self._signature:
                self._signature = signature
                self.render_content.refresh()
        except Exception as exc:
            self.sync_label.text = (
                "Connexion Excel interrompue"
            )
            self.sync_label.classes(
                remove="sync-ok", add="sync-bad"
            )
            print(f"Auto-refresh Excel: {exc}")

    async def manual_refresh(self) -> None:
        try:
            self.repo.connect()
            self.sync_label.text = "Excel connecté"
            self.sync_label.classes(remove="sync-bad", add="sync-ok")
            self.source_label.text = self._source_text()
            self._signature = self._signature_for_current_page()
            self.render_content.refresh()
            ui.notify("Données relues depuis Excel", type="positive")
        except Exception as exc:
            self.sync_label.text = "Excel non connecté"
            self.sync_label.classes(remove="sync-ok", add="sync-bad")
            ui.notify(str(exc), type="negative")

    def _render_content(self) -> None:
        if self.current_page == "settings":
            self.render_settings()
        elif self.current_page == "planning":
            self.operational_planning_page.render()
        elif self.current_page == "requests":
            self.demand_requests_page.render()
        elif self.current_page == "segments":
            self.segments_page.render()
        elif self.current_page == "data":
            self.render_data()
        else:
            self.render_dashboard()

    # ------------------------------------------------------------------
    # Paramètres / fichier Excel
    # ------------------------------------------------------------------
    def _source_text(self) -> str:
        return str(self.repo.path) if self.repo.path else "Non configuré"

    def render_settings(self) -> None:
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("Paramètres").classes("text-2xl font-bold")
                ui.label(
                    "Choisis le fichier Excel utilisé comme source de données."
                ).classes("muted")

        with ui.card().classes("section-card w-full max-w-4xl"):
            ui.label("Classeur Excel").classes("text-lg font-semibold")
            ui.label(
                "Pour OneDrive, utilise le chemin LOCAL synchronisé, par exemple : "
                r"C:\Users\VotreNom\OneDrive - Entreprise\Planification\PlanificationMoyenLongTerme.xlsx"
            ).classes("text-sm muted")
            ui.label(
                "Une URL https://...sharepoint.com ou onedrive.live.com n'est pas supportée par xlwings."
            ).classes("text-xs text-amber-700")

            self.workbook_path_input = ui.input(
                "Chemin du fichier .xlsx",
                value=str(self.repo.path) if self.repo.path else "",
                placeholder=r"C:\Users\...\OneDrive - ...\PlanificationMoyenLongTerme.xlsx",
            ).classes("w-full")

            with ui.row().classes("w-full items-center"):
                ui.button(
                    "Parcourir...", icon="folder_open", on_click=self.choose_workbook_file
                ).props("outline no-caps")
                ui.button(
                    "Tester et enregistrer", icon="save", on_click=self.save_workbook_setting
                ).props("unelevated no-caps color=primary")

            if self.repo.is_connected:
                ui.label("✓ Excel est actuellement connecté à ce fichier.").classes(
                    "text-sm text-green-700"
                )
            else:
                ui.label(
                    "Le fichier n'est pas encore connecté. Enregistre un chemin valide pour activer les autres écrans."
                ).classes("text-sm text-gray-600")

        with ui.card().classes("section-card w-full max-w-4xl"):
            ui.label("Utilisation avec OneDrive").classes("text-lg font-semibold")
            ui.markdown(
                """
- Le fichier peut être dans un dossier **OneDrive synchronisé sur le PC**.
- L'application travaille avec la copie locale OneDrive; le client OneDrive synchronise ensuite les changements vers Microsoft 365.
- Idéalement, active **Toujours conserver sur cet appareil** pour ce fichier/dossier afin d'éviter qu'il soit seulement disponible dans le nuage.
- Excel reste le moteur du classeur et l'application écrit via `xlwings`.
- Si plusieurs personnes modifient le même classeur simultanément, les conflits restent soumis aux limites de coédition/synchronisation d'Excel et OneDrive.
                """
            )

    def choose_workbook_file(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            filename = filedialog.askopenfilename(
                title="Choisir le classeur de planification",
                filetypes=[
                    ("Classeur Excel", "*.xlsx *.xlsm"),
                    ("Tous les fichiers", "*.*"),
                ],
            )
            root.destroy()
            if filename:
                self.workbook_path_input.value = filename
        except Exception as exc:
            ui.notify(
                "Le sélecteur Windows n'a pas pu s'ouvrir. Tu peux coller le chemin manuellement. "
                f"Détail : {exc}",
                type="warning",
            )

    def save_workbook_setting(self) -> None:
        from pathlib import Path

        raw = str(self.workbook_path_input.value or "").strip().strip('"')
        if not raw:
            ui.notify("Choisis un fichier Excel.", type="warning")
            return

        path = Path(raw).expanduser()
        if not path.exists():
            ui.notify(f"Fichier introuvable : {path}", type="negative")
            return
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            ui.notify("Le fichier doit être un .xlsx ou .xlsm.", type="negative")
            return

        try:
            self.repo.set_path(path)
            self.repo.connect()
            save_workbook_path(path)
            self.sync_label.text = "Excel connecté"
            self.sync_label.classes(remove="sync-bad", add="sync-ok")
            self.source_label.text = self._source_text()
            self._signature = self._signature_for_current_page()
            ui.notify("Chemin enregistré. Le classeur Excel est connecté.", type="positive")
            self.current_page = "dashboard"
            self.render_content.refresh()
        except Exception as exc:
            self.sync_label.text = "Excel non connecté"
            self.sync_label.classes(remove="sync-ok", add="sync-bad")
            ui.notify(str(exc), type="negative")

    # ------------------------------------------------------------------
    # Tableau de bord
    # ------------------------------------------------------------------
    def render_dashboard(self) -> None:
        demands = self.repo.demands()
        efforts = active_efforts_for_week(
            self.repo, week_start()
        )
        techs = self.repo.technicians()
        pending = [
            d
            for d in demands
            if d.get("Statut") == "Soumise"
        ]
        planning = [
            d
            for d in demands
            if d.get("Statut")
            == "En planification"
        ]

        with ui.row().classes(
            "w-full items-center"
        ):
            with ui.column().classes("gap-0"):
                ui.label(
                    "Tableau de bord"
                ).classes("text-2xl font-bold")
                ui.label(
                    "Semaine du "
                    + week_start().strftime("%d/%m/%Y")
                ).classes("muted")
            ui.space()
            ui.button(
                "Nouvelle demande",
                icon="add",
                on_click=self.open_new_request_dialog,
            ).props(
                "unelevated no-caps color=primary"
            )

        with ui.grid(columns=4).classes(
            "w-full gap-4"
        ):
            self.kpi(
                "À approuver",
                len(pending),
                "approval",
                "Demandes au statut Soumise",
            )
            self.kpi(
                "En planification",
                len(planning),
                "event_note",
                "Demandes approuvées à affecter",
            )
            self.kpi(
                "Efforts cette semaine",
                len(efforts),
                "view_timeline",
                "Affectations actives",
            )
            self.kpi(
                "Ressources",
                len(techs),
                "groups",
                "Techniciens détectés",
            )

        with ui.grid(columns=2).classes(
            "w-full gap-4"
        ):
            with ui.card().classes(
                "section-card w-full"
            ):
                ui.label(
                    "Charge estimée — semaine courante"
                ).classes("text-lg font-semibold")
                ui.label(
                    "Approximation : Efforts Prévus "
                    "répartis sur les jours ouvrables; "
                    "Capacity mensuelle ÷ 4,33."
                ).classes("text-xs muted")

                loads = weekly_load(
                    self.repo, week_start()
                )[:10]
                if not loads:
                    ui.label(
                        "Aucune ressource détectée."
                    ).classes("muted")

                for load in loads:
                    with ui.column().classes(
                        "w-full gap-1 mt-2"
                    ):
                        with ui.row().classes(
                            "w-full items-center"
                        ):
                            ui.label(
                                load["name"]
                            ).classes("font-medium")
                            ui.space()
                            text = (
                                f'{load["planned"]:.1f} h'
                            )
                            if load["pct"] is not None:
                                text += (
                                    f" / "
                                    f'{load["weekly_capacity"]:.1f} h'
                                    f" · {int(load['pct'])} %"
                                )
                            ui.label(text).classes(
                                "text-sm muted"
                            )

                        fraction = min(
                            max(
                                (load["pct"] or 0)
                                / 100,
                                0,
                            ),
                            1,
                        )
                        ui.linear_progress(
                            value=fraction
                        ).classes("w-full")
                        if (load["pct"] or 0) > 100:
                            ui.label(
                                "Surcharge estimée"
                            ).classes(
                                "text-xs text-red-700"
                            )

            with ui.card().classes(
                "section-card w-full"
            ):
                with ui.row().classes(
                    "w-full items-center"
                ):
                    ui.label(
                        "Demandes à approuver"
                    ).classes(
                        "text-lg font-semibold"
                    )
                    ui.space()
                    ui.button(
                        "Voir tout",
                        on_click=lambda: (
                            self.navigate("requests")
                        ),
                    ).props("flat no-caps")

                if not pending:
                    ui.label(
                        "Aucune demande en attente."
                    ).classes("muted")

                for demand in pending[:8]:
                    with ui.row().classes(
                        "w-full items-center "
                        "border-b border-gray-100 py-2"
                    ):
                        with ui.column().classes(
                            "gap-0"
                        ):
                            ui.label(
                                str(
                                    demand.get(
                                        "NoDemande"
                                    )
                                    or ""
                                )
                            ).classes("font-semibold")
                            ui.label(
                                f"{demand.get('NumeroProjet') or '—'}"
                                f" · "
                                f"{demand.get('NomProjet') or ''}"
                            ).classes("text-sm")
                        ui.space()
                        ui.label(
                            str(
                                demand.get(
                                    "Priorite"
                                )
                                or "Normale"
                            )
                        ).classes("text-xs muted")

    def kpi(
        self,
        title: str,
        value: int | str,
        icon: str,
        subtitle: str,
    ) -> None:
        with ui.card().classes(
            "kpi-card w-full"
        ):
            with ui.row().classes(
                "w-full items-start"
            ):
                with ui.column().classes("gap-2"):
                    ui.label(title).classes(
                        "text-sm muted"
                    )
                    ui.label(
                        str(value)
                    ).classes("kpi-value")
                    ui.label(
                        subtitle
                    ).classes("text-xs muted")
                ui.space()
                ui.icon(
                    icon, size="34px"
                ).classes("text-blue-600")

    # ------------------------------------------------------------------
    # Planification style Shifts
    # ------------------------------------------------------------------
    def render_planning(self) -> None:
        days = week_days(self.current_week)
        techs = self.repo.technicians()
        efforts = self.repo.efforts(
            include_closed=False
        )

        with ui.row().classes(
            "w-full items-center"
        ):
            with ui.column().classes("gap-0"):
                ui.label(
                    "Planification"
                ).classes("text-2xl font-bold")
                ui.label(
                    "Vue ressources — style Shifts"
                ).classes("muted")
            ui.space()
            ui.button(
                icon="chevron_left",
                on_click=self.previous_week,
            ).props("flat round")
            ui.button(
                "Aujourd'hui",
                on_click=self.today_week,
            ).props("outline no-caps")
            ui.button(
                icon="chevron_right",
                on_click=self.next_week,
            ).props("flat round")
            ui.label(
                f"{days[0].strftime('%d %b')} – "
                f"{days[-1].strftime('%d %b %Y')}"
            ).classes("font-semibold ml-2")

        with ui.scroll_area().classes(
            "w-full h-[calc(100vh-190px)]"
        ):
            with ui.grid(columns=8).classes(
                "schedule-grid gap-0"
            ):
                with ui.column().classes(
                    "day-header p-3 justify-center"
                ):
                    ui.label(
                        "Ressource"
                    ).classes("font-semibold")

                for day in days:
                    with ui.column().classes(
                        "day-header p-2 items-center "
                        "justify-center"
                    ):
                        ui.label(
                            day.strftime(
                                "%a"
                            ).capitalize()
                        ).classes(
                            "text-xs uppercase muted"
                        )
                        ui.label(
                            day.strftime("%d")
                        ).classes(
                            "text-xl font-semibold"
                        )

                for tech_index, tech in enumerate(
                    techs
                ):
                    with ui.column().classes(
                        "resource-cell p-3 "
                        "justify-center gap-1"
                    ):
                        ui.label(
                            tech["name"]
                        ).classes("font-semibold")
                        details = " · ".join(
                            v
                            for v in [
                                tech.get("description"),
                                tech.get("team"),
                            ]
                            if v
                        )
                        ui.label(
                            details or "Ressource"
                        ).classes("text-xs muted")

                    tech_efforts = [
                        e
                        for e in efforts
                        if str(
                            e.get(
                                "Équipe/Technicien attitré"
                            )
                            or ""
                        ).strip()
                        == tech["name"]
                    ]

                    for day in days:
                        extra = (
                            " weekend-cell"
                            if day.weekday() >= 5
                            else ""
                        )
                        with ui.column().classes(
                            f"day-cell gap-1{extra}"
                        ):
                            day_efforts = [
                                e
                                for e in tech_efforts
                                if effort_overlaps_day(
                                    e, day
                                )
                            ]

                            for effort_index, effort in enumerate(
                                day_efforts
                            ):
                                css = PASTEL_CLASSES[
                                    (
                                        tech_index
                                        + effort_index
                                    )
                                    % len(PASTEL_CLASSES)
                                ]
                                with ui.element(
                                    "div"
                                ).classes(
                                    f"shift-card {css}"
                                ).on(
                                    "click",
                                    lambda _,
                                    e=effort: (
                                        self.open_effort_dialog(
                                            e
                                        )
                                    ),
                                ):
                                    ui.label(
                                        f"{effort.get('N° projet') or '—'}"
                                        f" · "
                                        f"{effort.get('Projet') or ''}"
                                    ).classes(
                                        "text-xs font-semibold"
                                    )
                                    ui.label(
                                        str(
                                            effort.get(
                                                "Précision"
                                            )
                                            or effort.get(
                                                "Compétence"
                                            )
                                            or "Affectation"
                                        )
                                    ).classes("text-xs")
                                    effort_hours = effort.get(
                                        "Efforts Prévus"
                                    )
                                    if effort_hours:
                                        ui.label(
                                            f"{effort_hours:g} h"
                                        ).classes(
                                            "text-[11px] muted"
                                        )

    def previous_week(self) -> None:
        self.current_week -= timedelta(days=7)
        self.render_content.refresh()

    def next_week(self) -> None:
        self.current_week += timedelta(days=7)
        self.render_content.refresh()

    def today_week(self) -> None:
        self.current_week = week_start()
        self.render_content.refresh()

    def open_effort_dialog(
        self, effort: dict[str, Any]
    ) -> None:
        self.interaction_lock = True
        tech_options = [
            t["name"]
            for t in self.repo.technicians()
        ]

        with ui.dialog() as dialog, ui.card().classes(
            "w-[650px] max-w-full"
        ):
            ui.label(
                "Modifier l'affectation — "
                f"{effort.get('N° projet') or ''}"
            ).classes("text-xl font-bold")
            ui.label(
                str(effort.get("Projet") or "")
            ).classes("muted")

            precision = ui.input(
                "Précision",
                value=str(
                    effort.get("Précision") or ""
                ),
            ).classes("w-full")

            technician = ui.select(
                tech_options,
                label="Technicien",
                value=effort.get(
                    "Équipe/Technicien attitré"
                ),
            ).classes("w-full")

            with ui.row().classes("w-full"):
                start = ui.input(
                    "Début",
                    value=self._date_text(
                        effort.get("Date de début")
                    ),
                ).props("type=date").classes("flex-1")
                end = ui.input(
                    "Fin",
                    value=self._date_text(
                        effort.get("Date de fin")
                    ),
                ).props("type=date").classes("flex-1")

            with ui.row().classes("w-full"):
                status_value = str(
                    effort.get("Status") or "EN COURS"
                ).upper()
                if status_value not in EFFORT_STATUSES:
                    status_value = "EN COURS"

                status = ui.select(
                    EFFORT_STATUSES,
                    label="Statut",
                    value=status_value,
                ).classes("flex-1")
                hours = ui.number(
                    "Efforts prévus (h)",
                    value=effort.get(
                        "Efforts Prévus"
                    ),
                    min=0,
                ).classes("flex-1")

            note = ui.textarea(
                "Note",
                value=str(effort.get("Note") or ""),
            ).classes("w-full")

            def save() -> None:
                try:
                    self.repo.update_effort(
                        int(effort["_row"]),
                        {
                            "Précision": (
                                precision.value
                            ),
                            "Équipe/Technicien attitré": (
                                technician.value
                            ),
                            "Date de début": start.value,
                            "Date de fin": end.value,
                            "Status": status.value,
                            "Efforts Prévus": hours.value,
                            "Note": note.value,
                        },
                    )
                    self._signature = (
                        self._signature_for_current_page()
                    )
                    ui.notify(
                        "Affectation mise à jour dans Excel",
                        type="positive",
                    )
                    dialog.close()
                    self.render_content.refresh()
                except Exception as exc:
                    ui.notify(
                        str(exc), type="negative"
                    )

            with ui.row().classes(
                "w-full justify-end"
            ):
                ui.button(
                    "Annuler",
                    on_click=dialog.close,
                ).props("flat no-caps")
                ui.button(
                    "Enregistrer",
                    icon="save",
                    on_click=save,
                ).props(
                    "unelevated no-caps color=primary"
                )

        dialog.on(
            "hide", lambda _: self._unlock()
        )
        dialog.open()

    # ------------------------------------------------------------------
    # Demandes / approbations
    # ------------------------------------------------------------------



    # ------------------------------------------------------------------
    # Gestion générique Excel
    # ------------------------------------------------------------------
    def render_data(self) -> None:
        sheet_names = self.repo.sheet_names()
        if self.selected_sheet not in sheet_names:
            self.selected_sheet = sheet_names[0]

        grid_model = self.repo.read_sheet_grid(
            self.selected_sheet
        )

        with ui.row().classes(
            "w-full items-center"
        ):
            with ui.column().classes("gap-0"):
                ui.label(
                    "Données Excel"
                ).classes("text-2xl font-bold")
                ui.label(
                    "Édition directe du classeur. "
                    "Les formules sont protégées."
                ).classes("muted")

            ui.space()

            if self.selected_sheet in MASTER_SHEETS:
                ui.button(
                    "Ajouter une ligne",
                    icon="add",
                    on_click=self.add_blank_row,
                ).props("outline no-caps")

            sheet_select = ui.select(
                sheet_names,
                value=self.selected_sheet,
                label="Feuille",
            ).classes("w-72")

            def change_sheet(e: Any) -> None:
                self.selected_sheet = str(e.value)
                self._signature = (
                    self._signature_for_current_page()
                )
                self.render_content.refresh()

            sheet_select.on_value_change(
                change_sheet
            )

        if not grid_model.columns:
            ui.label(
                "Cette feuille ne contient aucune "
                "plage de données détectable."
            ).classes("muted")
            return

        grid = ui.aggrid(
            {
                "columnDefs": grid_model.columns,
                "rowData": grid_model.rows,
                "defaultColDef": {
                    "sortable": True,
                    "filter": True,
                    "resizable": True,
                },
                "animateRows": False,
                "stopEditingWhenCellsLoseFocus": True,
                "undoRedoCellEditing": True,
            }
        ).classes(
            "w-full h-[calc(100vh-210px)]"
        )

        def cell_changed(e: Any) -> None:
            if not isinstance(e.args, dict):
                return

            args = e.args
            data = args.get("data") or {}
            col_id = (
                args.get("colId")
                or (
                    args.get("colDef") or {}
                ).get("field")
                or (
                    args.get("column") or {}
                ).get("colId")
            )
            if col_id not in grid_model.field_to_col:
                return

            new_value = args.get(
                "newValue",
                data.get(col_id),
            )

            try:
                self.repo.update_sheet_cell(
                    self.selected_sheet,
                    int(data["_excel_row"]),
                    int(
                        grid_model.field_to_col[
                            col_id
                        ]
                    ),
                    new_value,
                )
                self._signature = (
                    self._signature_for_current_page()
                )
                ui.notify(
                    "Excel mis à jour",
                    type="positive",
                    timeout=900,
                )
            except Exception as exc:
                ui.notify(
                    str(exc), type="negative"
                )
                self.render_content.refresh()

        grid.on(
            "cellValueChanged", cell_changed
        )

        mode = (
            "édition"
            if self.selected_sheet in MASTER_SHEETS
            else "lecture seule"
        )
        ui.label(
            f"Feuille : {self.selected_sheet} · "
            f"en-tête détecté : ligne "
            f"{grid_model.header_row} · "
            f"mode : {mode} · "
            f"sync auto : "
            f"{self.refresh_seconds:g} s"
        ).classes("text-xs muted")

    def add_blank_row(self) -> None:
        try:
            row = self.repo.append_blank_row(
                self.selected_sheet
            )
            self._signature = (
                self._signature_for_current_page()
            )
            ui.notify(
                f"Ligne Excel {row} ajoutée",
                type="positive",
            )
            self.render_content.refresh()
        except Exception as exc:
            ui.notify(str(exc), type="negative")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _after_write(
        self, message: str | None = None
    ) -> None:
        self._signature = (
            self._signature_for_current_page()
        )
        if message:
            ui.notify(
                message, type="positive"
            )
        self.render_content.refresh()

    def _unlock(self) -> None:
        self.interaction_lock = False
        self._signature = (
            self._signature_for_current_page()
        )

    @staticmethod
    def _date_text(value: Any) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if value:
            return str(value)[:10]
        return ""

