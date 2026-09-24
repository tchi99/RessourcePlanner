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
from .project_source import AcumaticaProjectSource, AcumaticaProjectSourceSettings

__all__ = [
    "AcumaticaProjectSource",
    "AcumaticaProjectSourceSettings",
    "ODataProjectFeedError",
    "ODataProjectRecord",
    "ODataProjectSource",
    "ODataProjectSourceSettings",
    "parse_rp_projects_feed",
]
