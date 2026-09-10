from __future__ import annotations

from nicegui import ui

from .medium_term_capacity import render_medium_term_with_projected_capacity
from .medium_term_page import register_medium_term_renderer


MEDIUM_TERM_CSS = """
.v18-gantt-scroll { overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 10px; }
.v18-gantt-grid { display:grid; grid-template-columns:340px 1280px; min-width:1620px; background:white; }
.v18-sticky { position:sticky; left:0; z-index:4; background:white; }
.v18-header-label { padding:8px 10px; border-bottom:1px solid #d1d5db; }
.v18-week-header { display:grid; grid-template-columns:repeat(16,1fr); border-bottom:1px solid #d1d5db; }
.v18-week-cell { padding:5px 2px; text-align:center; border-left:1px solid #e5e7eb; min-height:38px; }
.v18-group-label { padding:7px 10px; background:#f3f4f6; border-top:1px solid #d1d5db; border-bottom:1px solid #d1d5db; }
.v18-group-fill { background:#f3f4f6; border-top:1px solid #d1d5db; border-bottom:1px solid #d1d5db; }
.v18-effort-label { padding:7px 10px; border-bottom:1px solid #e5e7eb; cursor:pointer; min-height:58px; }
.v18-effort-label:hover { background:#f8fafc; }
.v18-timeline-row { position:relative; border-bottom:1px solid #e5e7eb;
    background-image:linear-gradient(to right,#e5e7eb 1px,transparent 1px);
    background-size:6.25% 100%; overflow:hidden; }
.v18-current-week { position:absolute; top:0; bottom:0; background:rgba(59,130,246,.06); z-index:0; }
.v18-macro-bar { position:absolute; top:7px; height:18px; background:#dbeafe; border:1px solid #93c5fd;
    border-radius:5px; overflow:hidden; z-index:1; }
.v18-segment-bar { position:absolute; height:18px; z-index:2; }
.v18-capacity-scroll { overflow-x:auto; width:100%; }
.v18-capacity-grid { display:grid; grid-template-columns:180px repeat(16,72px); min-width:1332px; align-items:center; gap:2px; }
.v18-capacity-label { padding:4px 6px; background:white; z-index:3; }
@supports selector(.q-scrollarea:has(.schedule-grid)) {
  .q-scrollarea:has(.schedule-grid) {
    height: clamp(620px, calc(100vh - 210px), 920px) !important;
  }
}
.schedule-grid {
  grid-template-columns: 190px repeat(7, minmax(165px, 1fr)) !important;
  min-width: 1345px !important;
}
"""


def install_medium_term_renderer_compat() -> None:
    """Publish the projected-capacity V1 renderer behind the explicit page boundary."""

    register_medium_term_renderer(render_medium_term_with_projected_capacity)
    ui.add_css(MEDIUM_TERM_CSS)
