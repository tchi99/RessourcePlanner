from __future__ import annotations

from sqlalchemy import Index, text

from .models import Resource


RESOURCE_EXTERNAL_ID_INDEX = Index(
    "ux_resources_external_id_not_null",
    Resource.external_id,
    unique=True,
    sqlite_where=text("external_id IS NOT NULL"),
    mssql_where=text("external_id IS NOT NULL"),
)
