from __future__ import annotations

from sqlalchemy import Index

from .models import ResourceRequirement, WorkforceRequest


# These identifiers remain the stable human/business IDs through the V1 → SQL
# cutover. Internal UUID primary keys stay separate for relationships.
WORKFORCE_REQUEST_NUMBER_INDEX = Index(
    "ux_workforce_requests_demand_number",
    WorkforceRequest.legacy_demand_number,
    unique=True,
)
RESOURCE_REQUIREMENT_NUMBER_INDEX = Index(
    "ux_resource_requirements_segment_id",
    ResourceRequirement.legacy_segment_id,
    unique=True,
)

__all__ = [
    "RESOURCE_REQUIREMENT_NUMBER_INDEX",
    "WORKFORCE_REQUEST_NUMBER_INDEX",
]
