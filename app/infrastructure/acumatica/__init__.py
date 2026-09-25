"""Acumatica integration adapters.

The rest of RessourcePlanner depends on application ports, not on these HTTP details.
"""

from .odata_project_source import (
    ODataProjectFeedError,
    ODataProjectRecord,
    ODataProjectSource,
    ODataProjectSourceSettings,
    parse_rp_projects_feed,
)
from .odata_project_task_source import (
    ODataProjectTaskFeedError,
    ODataProjectTaskRecord,
    ODataProjectTaskSource,
    ODataProjectTaskSourceSettings,
    parse_rp_project_tasks_feed,
)
from .project_source import AcumaticaProjectSource, AcumaticaProjectSourceSettings

__all__ = [
    "AcumaticaProjectSource",
    "AcumaticaProjectSourceSettings",
    "ODataProjectFeedError",
    "ODataProjectRecord",
    "ODataProjectSource",
    "ODataProjectTaskFeedError",
    "ODataProjectTaskRecord",
    "ODataProjectTaskSource",
    "ODataProjectTaskSourceSettings",
    "ODataProjectSourceSettings",
    "parse_rp_project_tasks_feed",
    "parse_rp_projects_feed",
]
