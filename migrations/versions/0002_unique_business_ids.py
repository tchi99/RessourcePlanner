"""Enforce unique business identifiers for demands and segments.

Revision ID: 0002_unique_business_ids
Revises: 0001_initial_planning_schema
Create Date: 2026-08-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_unique_business_ids"
down_revision: Union[str, Sequence[str], None] = "0001_initial_planning_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing development databases created by 0001 may contain null compatibility
    # identifiers. Backfill them with the internal UUID before adding unique indexes;
    # the one-shot V1 importer will supply the real DMO/SEG identifiers at cutover.
    op.execute(
        sa.text(
            "UPDATE workforce_requests "
            "SET legacy_demand_number = id "
            "WHERE legacy_demand_number IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE resource_requirements "
            "SET legacy_segment_id = id "
            "WHERE legacy_segment_id IS NULL"
        )
    )
    op.create_index(
        "ux_workforce_requests_demand_number",
        "workforce_requests",
        ["legacy_demand_number"],
        unique=True,
    )
    op.create_index(
        "ux_resource_requirements_segment_id",
        "resource_requirements",
        ["legacy_segment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_resource_requirements_segment_id",
        table_name="resource_requirements",
    )
    op.drop_index(
        "ux_workforce_requests_demand_number",
        table_name="workforce_requests",
    )
