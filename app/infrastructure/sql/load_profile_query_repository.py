from __future__ import annotations

from .active_days_query_repository import SqlPlannerQueryRepositoryWithEstimatedDays
from .models import ResourceRequirement
from ...domain.load_profiles import LOAD_PROFILE_UNIFORM, normalize_load_profile


class SqlPlannerQueryRepositoryWithLoadProfiles(SqlPlannerQueryRepositoryWithEstimatedDays):
    """Canonical reads and #35 preview enriched with the segment load profile."""

    def _segment_row(self, **kwargs):
        row = super()._segment_row(**kwargs)
        requirement = kwargs.get("requirement")
        profile = (
            requirement.load_profile
            if isinstance(requirement, ResourceRequirement)
            else LOAD_PROFILE_UNIFORM
        )
        return {**row, "ProfilCharge": normalize_load_profile(profile)}
