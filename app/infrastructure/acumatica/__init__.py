"""Acumatica integration adapters.

The rest of RessourcePlanner depends on application ports, not on these HTTP details.
"""

from .odata_employee_source import (
    ODataEmployeeFeedError,
    ODataEmployeeRecord,
    ODataEmployeeSource,
    ODataEmployeeSourceSettings,
    parse_rp_employees_feed,
)
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
    "ODataEmployeeFeedError",
    "ODataEmployeeRecord",
    "ODataEmployeeSource",
    "ODataEmployeeSourceSettings",
    "ODataProjectFeedError",
    "ODataProjectRecord",
    "ODataProjectSource",
    "ODataProjectSourceSettings",
    "parse_rp_employees_feed",
    "parse_rp_projects_feed",
]
