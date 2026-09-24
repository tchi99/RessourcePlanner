from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...application.errors import ApplicationConflictError
from .models import WorkforceRequest


def acquire_request_aggregate_version(
    session: Session,
    request: WorkforceRequest,
    expected_version: int,
) -> int:
    """Acquire the WorkforceRequest CAS shared by request-scoped mutations."""

    expected = int(expected_version)
    result = session.execute(
        update(WorkforceRequest)
        .where(
            WorkforceRequest.id == request.id,
            WorkforceRequest.aggregate_version == expected,
        )
        .values(
            aggregate_version=WorkforceRequest.aggregate_version + 1
        )
    )
    if int(result.rowcount or 0) != 1:
        actual = session.scalar(
            select(WorkforceRequest.aggregate_version).where(
                WorkforceRequest.id == request.id
            )
        )
        raise ApplicationConflictError(
            "La demande a été modifiée depuis sa lecture.",
            code="demand_version_conflict",
            context={
                "demand_number": (
                    str(request.legacy_demand_number or "").strip()
                    or request.id
                ),
                "expected_version": expected,
                "current_version": int(
                    actual or request.aggregate_version or 1
                ),
            },
        )

    session.flush()
    session.refresh(request, attribute_names=["aggregate_version"])
    return int(request.aggregate_version or expected + 1)
