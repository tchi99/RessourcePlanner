from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def remove_top_level_functions(source: str, names: set[str]) -> str:
    tree = ast.parse(source)
    ranges: list[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            ranges.append((node.lineno, node.end_lineno or node.lineno))
    lines = source.splitlines(keepends=True)
    for start, end in sorted(ranges, reverse=True):
        del lines[start - 1 : end]
    return "".join(lines)


def update_v13() -> None:
    path = APP / "v13.py"
    source = path.read_text(encoding="utf-8")

    old_constants = '''SEGMENT_SHEET = "SegmentsMO"\nSEGMENT_TABLE = "SegmentsMOTable"\nSEGMENT_HEADERS = [\n    "IDSegment",\n    "NoDemande",\n    "NumeroProjet",\n    "NomProjet",\n    "Technicien",\n    "DateDebut",\n    "DateFin",\n    "HeuresPrevues",\n    "Statut",\n    "Description",\n    "SourceEffortRow",\n    "DateCreation",\n    "DateModification",\n    "CreePar",\n]\nSEGMENT_STATUSES = ["Planifié", "En cours", "Terminé", "Annulé"]\n'''
    if old_constants not in source:
        raise RuntimeError("v13 segment constants block not found")
    source = source.replace(old_constants, "", 1)

    import_anchor = "from .services import week_days, week_start\n"
    segment_import = '''from .segment_repository import (\n    SEGMENT_HEADERS,\n    SEGMENT_SHEET,\n    SEGMENT_STATUSES,\n    add_segment,\n    ensure_segment_sheet as _ensure_v13_sheets,\n    number as _number,\n    segment_records,\n    update_segment,\n)\n'''
    if segment_import not in source:
        source = source.replace(import_anchor, import_anchor + segment_import, 1)

    source = remove_top_level_functions(
        source,
        {
            "_ensure_v13_sheets",
            "_number",
            "_excel_datetime",
            "segment_records",
            "_next_segment_id",
            "add_segment",
            "update_segment",
            "_render_segments",
            "_clear_segment_filter",
            "_go_to_segments",
        },
    )

    nav_block = '''    if not any(item[0] == "segments" for item in ui_module.NAV_ITEMS):\n        planning_index = next(\n            (index for index, item in enumerate(ui_module.NAV_ITEMS) if item[0] == "planning"), 2\n        )\n        ui_module.NAV_ITEMS.insert(planning_index + 1, ("segments", "view_timeline", "Segments"))\n\n'''
    source = source.replace(nav_block, "", 1)

    render_branch = '''        if self.current_page == "segments":\n            _render_segments(self)\n            return\n'''
    source = source.replace(render_branch, "", 1)

    sheets_branch = '''        if self.current_page == "segments":\n            return [SEGMENT_SHEET, "DemandesMO", features.AVAILABILITY_SHEET, "Liste_Effort"]\n'''
    source = source.replace(sheets_branch, "", 1)

    source = source.replace(
        "    ui_module.PlannerUI.render_segments = _render_segments\n",
        "",
        1,
    )
    path.write_text(source, encoding="utf-8")


def update_ui() -> None:
    path = APP / "ui.py"
    source = path.read_text(encoding="utf-8")

    source = source.replace(
        "from .demand_requests_page import DemandRequestsPage\n",
        "from .demand_requests_page import DemandRequestsPage\n"
        "from .segment_repository import SEGMENT_SHEET\n"
        "from .segments_page import SegmentsPage\n",
        1,
    )
    source = source.replace(
        '    ("planning", "calendar_month", "Planification"),\n',
        '    ("planning", "calendar_month", "Planification"),\n'
        '    ("segments", "view_timeline", "Segments"),\n',
        1,
    )
    source = source.replace(
        "        self.demand_requests_page = DemandRequestsPage(self)\n",
        "        self.demand_requests_page = DemandRequestsPage(self)\n"
        "        self.segments_page = SegmentsPage(self)\n",
        1,
    )
    requests_sheets = '''        if self.current_page == "requests":\n            return [\n                "DemandesMO",\n                "Historique",\n                "Liste des projets",\n            ]\n'''
    segment_sheets = requests_sheets + '''        if self.current_page == "segments":\n            return [SEGMENT_SHEET, "DemandesMO", "Disponibilites", "Liste_Effort"]\n'''
    if requests_sheets not in source:
        raise RuntimeError("ui requests sheets branch not found")
    source = source.replace(requests_sheets, segment_sheets, 1)

    requests_render = '''        elif self.current_page == "requests":\n            self.demand_requests_page.render()\n'''
    segment_render = requests_render + '''        elif self.current_page == "segments":\n            self.segments_page.render()\n'''
    if requests_render not in source:
        raise RuntimeError("ui requests render branch not found")
    source = source.replace(requests_render, segment_render, 1)
    path.write_text(source, encoding="utf-8")


def update_demand_requests_page() -> None:
    path = APP / "demand_requests_page.py"
    source = path.read_text(encoding="utf-8")

    source = source.replace(
        "from .application.runtime_services import demand_service\n",
        "from .application.runtime_services import demand_service\n"
        "from .segment_repository import number, segment_records\n",
        1,
    )
    source = remove_top_level_functions(source, {"_number", "_segment_records"})
    source = source.replace("_segment_records(self.owner.repo)", "segment_records(self.owner.repo)")
    source = source.replace("_number(segment.get(\"HeuresPrevues\"))", "number(segment.get(\"HeuresPrevues\"))")

    old_go = '''    def _go_to_segments(self, demand: dict[str, Any]) -> None:\n        self.owner.segment_request_filter = str(demand.get("NoDemande") or "")\n        self.owner.current_page = "segments"\n        self.owner.selected_request = None\n        self.owner._signature = self.owner._signature_for_current_page()\n        self.owner.render_content.refresh()\n'''
    new_go = '''    def _go_to_segments(self, demand: dict[str, Any]) -> None:\n        self.owner.segments_page.open_for_demand(demand)\n'''
    if old_go not in source:
        raise RuntimeError("DemandRequestsPage segment navigation block not found")
    source = source.replace(old_go, new_go, 1)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    update_v13()
    update_ui()
    update_demand_requests_page()


if __name__ == "__main__":
    main()
