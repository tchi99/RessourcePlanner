from __future__ import annotations

from . import v13, v18
from .effort_identity_migrations import (
    EffortIdentityMigrationReport,
    ensure_effort_identity_schema_controlled,
    ensure_effort_ids_controlled,
)
from .excel_repository import DEMAND_HEADERS, MASTER_SHEETS, ExcelRepository
from .infrastructure.excel.data_migrations import ExcelDataMigrationReport
from .infrastructure.excel.schema_migrations import ExcelSchemaMigrationReport


EFFORT_ID_FIELD = v18.EFFORT_ID_FIELD
SOURCE_EFFORT_ID_FIELD = v18.SOURCE_EFFORT_ID_FIELD
EFFORT_SHEET = v18.EFFORT_SHEET


def _declare_effort_identity_fields() -> None:
    if SOURCE_EFFORT_ID_FIELD not in DEMAND_HEADERS:
        DEMAND_HEADERS.append(SOURCE_EFFORT_ID_FIELD)
    if SOURCE_EFFORT_ID_FIELD not in v13.SEGMENT_HEADERS:
        v13.SEGMENT_HEADERS.append(SOURCE_EFFORT_ID_FIELD)
    MASTER_SHEETS.add(EFFORT_SHEET)


def _unchanged_effort_identity_report() -> EffortIdentityMigrationReport:
    return EffortIdentityMigrationReport(
        schema=ExcelSchemaMigrationReport(migration_ids=(), changed_migration_ids=()),
        data=ExcelDataMigrationReport(migration_ids=(), change_counts=()),
    )


def ensure_effort_ids(repo: ExcelRepository) -> dict[int, str]:
    """Ensure stable identities for directly edited Liste_Effort rows."""

    return ensure_effort_ids_controlled(repo)


def ensure_effort_identity_schema(
    repo: ExcelRepository,
) -> EffortIdentityMigrationReport:
    """Run the full migration once per workbook/header shape."""

    _declare_effort_identity_fields()
    marker = (str(repo.path or ""), tuple(DEMAND_HEADERS), tuple(v13.SEGMENT_HEADERS))
    if getattr(repo, "_v18_schema_ready", None) == marker:
        return _unchanged_effort_identity_report()

    report = ensure_effort_identity_schema_controlled(repo)
    repo._v18_schema_ready = marker
    return report


def install_effort_identity_compat() -> None:
    """Install V1.8 stable-link behavior over controlled migrations."""

    if getattr(ExcelRepository, "_effort_identity_compat_installed", False):
        return

    _declare_effort_identity_fields()

    # V1.8 business wrappers resolve these module globals at execution time. Point
    # only their migration hooks at the controlled implementation before installing
    # the wrappers; stable-link behavior remains otherwise unchanged.
    v18._ensure_effort_ids = ensure_effort_ids_controlled
    v18.ensure_v18_schema = ensure_effort_identity_schema
    v18._install_stable_link_wrappers()
    ExcelRepository._effort_identity_compat_installed = True
