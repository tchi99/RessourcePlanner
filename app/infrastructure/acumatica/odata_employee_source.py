from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import logging
from typing import Final
from urllib.parse import urljoin

import httpx

from ...application import ApplicationOperationError, EmployeeSourcePort, ExternalEmployeeRecord
from .odata_atom import (
    ODataAtomFeedError,
    classify_http_failure as _http_failure_kind,
    optional_text as _optional_text,
    parse_atom_feed,
)


logger = logging.getLogger(__name__)

_INT32_MIN: Final = -(2**31)
_INT32_MAX: Final = 2**31 - 1


class ODataEmployeeFeedError(ValueError):
    """Contract error without retaining or exposing the offending employee value."""

    def __init__(
        self,
        reason: str,
        *,
        field: str | None = None,
        entry_index: int | None = None,
    ) -> None:
        self.reason = reason
        self.field = field
        self.entry_index = entry_index
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ODataEmployeeRecord:
    employee_id: str
    display_name: str
    email: str | None
    status: str
    department_description: str | None
    department_code: str | None
    employee_class: str | None
    supervisor_id: str | None
    telephone: str | None
    branch_code: str | None
    contact_id: int | None

    def to_external_record(self) -> ExternalEmployeeRecord:
        return ExternalEmployeeRecord(
            external_id=self.employee_id,
            display_name=self.display_name,
            email=self.email,
            erp_status=self.status,
            erp_active=self.status.casefold() == "actif",
            department_description=self.department_description,
            department_code=self.department_code,
            employee_class=self.employee_class,
            supervisor_external_id=self.supervisor_id,
            telephone=self.telephone,
            branch_code=self.branch_code,
            contact_id=self.contact_id,
        )


def _required_text(
    values: Mapping[str, str | None],
    field: str,
    *,
    entry_index: int,
) -> str:
    value = _optional_text(values.get(field))
    if value is None:
        raise ODataEmployeeFeedError(
            "required_field_missing",
            field=field,
            entry_index=entry_index,
        )
    return value


def _parse_optional_int32(
    value: str | None,
    field: str,
    *,
    entry_index: int,
) -> int | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        parsed = int(text, 10)
    except (TypeError, ValueError) as exc:
        raise ODataEmployeeFeedError(
            "invalid_int32",
            field=field,
            entry_index=entry_index,
        ) from exc
    if not _INT32_MIN <= parsed <= _INT32_MAX:
        raise ODataEmployeeFeedError(
            "invalid_int32",
            field=field,
            entry_index=entry_index,
        )
    return parsed


def parse_rp_employees_feed(xml_payload: bytes | str) -> tuple[ODataEmployeeRecord, ...]:
    """Parse one complete RP_Employees Atom feed using the shared OData envelope."""

    try:
        feed = parse_atom_feed(xml_payload)
    except ODataAtomFeedError as exc:
        raise ODataEmployeeFeedError(
            exc.reason,
            entry_index=exc.entry_index,
        ) from exc

    records: list[ODataEmployeeRecord] = []
    for entry_index, entry in enumerate(feed.entries):
        values = entry.values()
        records.append(
            ODataEmployeeRecord(
                employee_id=_required_text(values, "EmployeID", entry_index=entry_index),
                display_name=_required_text(values, "DisplayName", entry_index=entry_index),
                email=_optional_text(values.get("Email")),
                status=_required_text(values, "Status", entry_index=entry_index),
                department_description=_optional_text(
                    values.get("DepartmentCodeDescription")
                ),
                department_code=_optional_text(values.get("DepartementCode")),
                employee_class=_optional_text(values.get("EmployeeClass")),
                supervisor_id=_optional_text(values.get("SupervisordID")),
                telephone=_optional_text(values.get("Telephone")),
                branch_code=_optional_text(values.get("BranchCode")),
                contact_id=_parse_optional_int32(
                    values.get("ContactID"),
                    "ContactID",
                    entry_index=entry_index,
                ),
            )
        )
    return tuple(records)


@dataclass(frozen=True, slots=True)
class ODataEmployeeSourceSettings:
    """Runtime settings for the RP_Employees OData contract."""

    base_url: str
    feed_path: str = "/oDATA/RP_Employees"
    timeout_seconds: float = 30.0
    page_size: int = 100
    username: str | None = field(default=None, repr=False)
    credential: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.page_size <= 0:
            raise ValueError("page_size must be positive")
        if bool(self.username) != bool(self.credential):
            raise ValueError("username and credential must be configured together")

    def safe_summary(self) -> dict[str, object]:
        return {
            "protocol": "odata",
            "feed_path": self.feed_path,
            "authentication": "basic" if self.username else "none",
            "pagination": {
                "mode": "top_skip",
                "orderby": "EmployeID asc",
                "page_size": self.page_size,
            },
        }


class ODataEmployeeSource(EmployeeSourcePort):
    """Read-only RP_Employees source using the same Atom/OData pattern as projects."""

    def __init__(
        self,
        settings: ODataEmployeeSourceSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        request_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._request_headers = dict(request_headers or {})

    def _url(self) -> str:
        base = self._settings.base_url.rstrip("/") + "/"
        return urljoin(base, self._settings.feed_path.lstrip("/"))

    def _safe_context(
        self,
        *,
        failure_kind: str,
        retryable: bool,
        http_status: int | None = None,
        reason: str | None = None,
        field: str | None = None,
        entry_index: int | None = None,
    ) -> dict[str, object]:
        context: dict[str, object] = {
            "protocol": "odata",
            "feed_path": self._settings.feed_path,
            "failure_kind": failure_kind,
            "retryable": retryable,
        }
        if http_status is not None:
            context["http_status"] = int(http_status)
        if reason:
            context["reason"] = reason
        if field:
            context["field"] = field
        if entry_index is not None:
            context["entry_index"] = int(entry_index)
        return context

    def _log_failure(
        self,
        *,
        failure_kind: str,
        retryable: bool,
        http_status: int | None = None,
        reason: str | None = None,
    ) -> None:
        logger.warning(
            "Acumatica OData employee read failed kind=%s retryable=%s status=%s feed=%s reason=%s",
            failure_kind,
            retryable,
            http_status if http_status is not None else "-",
            self._settings.feed_path,
            reason or "-",
        )

    def list_employees(self) -> tuple[ExternalEmployeeRecord, ...]:
        headers = {
            "Accept": "application/atom+xml, application/xml;q=0.9",
            **self._request_headers,
        }
        auth = (
            httpx.BasicAuth(self._settings.username, self._settings.credential)
            if self._settings.username and self._settings.credential
            else None
        )
        records: list[ODataEmployeeRecord] = []
        seen_employee_ids: set[str] = set()
        skip = 0
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._settings.timeout_seconds,
                follow_redirects=True,
                auth=auth,
            ) as client:
                while True:
                    response = client.get(
                        self._url(),
                        headers=headers,
                        params={
                            "$orderby": "EmployeID asc",
                            "$top": str(self._settings.page_size),
                            "$skip": str(skip),
                        },
                    )
                    response.raise_for_status()
                    try:
                        page = parse_rp_employees_feed(response.content)
                    except ODataEmployeeFeedError as exc:
                        self._log_failure(
                            failure_kind="invalid_payload",
                            retryable=False,
                            http_status=response.status_code,
                            reason=exc.reason,
                        )
                        raise ApplicationOperationError(
                            "La réponse OData Acumatica des employés est invalide.",
                            code="acumatica_employee_response_invalid",
                            context=self._safe_context(
                                failure_kind="invalid_payload",
                                retryable=False,
                                http_status=response.status_code,
                                reason=exc.reason,
                                field=exc.field,
                                entry_index=exc.entry_index,
                            ),
                        ) from exc

                    duplicate_id = next(
                        (
                            record.employee_id
                            for record in page
                            if record.employee_id in seen_employee_ids
                        ),
                        None,
                    )
                    page_ids = [record.employee_id for record in page]
                    if duplicate_id is None and len(page_ids) != len(set(page_ids)):
                        duplicate_id = next(
                            employee_id
                            for employee_id in page_ids
                            if page_ids.count(employee_id) > 1
                        )
                    if duplicate_id is not None:
                        self._log_failure(
                            failure_kind="invalid_payload",
                            retryable=False,
                            http_status=response.status_code,
                            reason="pagination_duplicate_employee",
                        )
                        raise ApplicationOperationError(
                            "La pagination OData Acumatica des employés est incohérente.",
                            code="acumatica_employee_response_invalid",
                            context=self._safe_context(
                                failure_kind="invalid_payload",
                                retryable=False,
                                http_status=response.status_code,
                                reason="pagination_duplicate_employee",
                            ),
                        )

                    records.extend(page)
                    seen_employee_ids.update(page_ids)
                    if len(page) < self._settings.page_size:
                        break
                    skip += len(page)
        except ApplicationOperationError:
            raise
        except httpx.HTTPStatusError as exc:
            status_code = int(exc.response.status_code)
            failure_kind, retryable = _http_failure_kind(status_code)
            self._log_failure(
                failure_kind=failure_kind,
                retryable=retryable,
                http_status=status_code,
            )
            raise ApplicationOperationError(
                "Impossible de lire les employés depuis Acumatica.",
                code="acumatica_employee_read_failed",
                context=self._safe_context(
                    failure_kind=failure_kind,
                    retryable=retryable,
                    http_status=status_code,
                ),
            ) from exc
        except httpx.TimeoutException as exc:
            self._log_failure(failure_kind="timeout", retryable=True)
            raise ApplicationOperationError(
                "Impossible de lire les employés depuis Acumatica.",
                code="acumatica_employee_read_failed",
                context=self._safe_context(failure_kind="timeout", retryable=True),
            ) from exc
        except httpx.RequestError as exc:
            self._log_failure(failure_kind="network", retryable=True)
            raise ApplicationOperationError(
                "Impossible de lire les employés depuis Acumatica.",
                code="acumatica_employee_read_failed",
                context=self._safe_context(failure_kind="network", retryable=True),
            ) from exc

        return tuple(record.to_external_record() for record in records)
