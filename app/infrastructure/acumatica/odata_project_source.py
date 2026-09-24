from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Final
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import httpx

from ...application import ApplicationOperationError, ExternalProjectRecord, ProjectSourcePort


logger = logging.getLogger(__name__)

ATOM_NAMESPACE: Final = "http://www.w3.org/2005/Atom"
DATA_NAMESPACE: Final = "http://schemas.microsoft.com/ado/2007/08/dataservices"
METADATA_NAMESPACE: Final = "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
_INT32_MIN: Final = -(2**31)
_INT32_MAX: Final = 2**31 - 1


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _http_failure_kind(status_code: int) -> tuple[str, bool]:
    if status_code == 401:
        return "authentication", False
    if status_code == 403:
        return "authorization", False
    if status_code == 429:
        return "throttled", True
    if status_code >= 500:
        return "upstream_5xx", True
    return "http_error", False


class ODataProjectFeedError(ValueError):
    """Contract error without retaining or exposing the offending business value."""

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
class ODataProjectRecord:
    project_id: int
    project_code: str
    project_name: str
    customer_id: str | None = None
    customer_name: str | None = None
    project_manager_id: str | None = None
    project_manager_name: str | None = None
    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    default_branch_code: str | None = None
    default_branch_description: str | None = None
    last_modified_at: datetime | None = None
    base_type: str | None = None

    def to_external_record(self) -> ExternalProjectRecord:
        return ExternalProjectRecord(
            external_id=str(self.project_id),
            number=self.project_code,
            name=self.project_name,
            client=self.customer_name,
            project_manager_external_id=self.project_manager_id,
            project_manager_name=self.project_manager_name,
            status=self.status or "active",
        )


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _property_values(properties: ET.Element) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for element in list(properties):
        if not element.tag.startswith(f"{{{DATA_NAMESPACE}}}"):
            continue
        name = _local_name(element.tag)
        is_null = _text(element.attrib.get(f"{{{METADATA_NAMESPACE}}}null")).casefold() == "true"
        values[name] = None if is_null else _optional_text(element.text)
    return values


def _required_text(values: Mapping[str, str | None], field: str, *, entry_index: int) -> str:
    value = _optional_text(values.get(field))
    if value is None:
        raise ODataProjectFeedError(
            "required_field_missing",
            field=field,
            entry_index=entry_index,
        )
    return value


def _parse_int32(value: str, field: str, *, entry_index: int) -> int:
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as exc:
        raise ODataProjectFeedError(
            "invalid_int32",
            field=field,
            entry_index=entry_index,
        ) from exc
    if not _INT32_MIN <= parsed <= _INT32_MAX:
        raise ODataProjectFeedError(
            "invalid_int32",
            field=field,
            entry_index=entry_index,
        )
    return parsed


def _parse_datetime(
    value: str | None,
    field: str,
    *,
    entry_index: int,
) -> datetime | None:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ODataProjectFeedError(
            "invalid_datetime",
            field=field,
            entry_index=entry_index,
        ) from exc


def parse_rp_projects_feed(xml_payload: bytes | str) -> tuple[ODataProjectRecord, ...]:
    """Parse one complete RP_Projects Atom feed without relying on XML prefixes."""

    try:
        root = ET.fromstring(xml_payload)
    except (ET.ParseError, TypeError, ValueError) as exc:
        raise ODataProjectFeedError("invalid_xml") from exc

    records: list[ODataProjectRecord] = []
    for entry_index, entry in enumerate(root.findall(f".//{{{ATOM_NAMESPACE}}}entry")):
        properties = entry.find(f".//{{{METADATA_NAMESPACE}}}properties")
        if properties is None:
            raise ODataProjectFeedError(
                "properties_missing",
                entry_index=entry_index,
            )
        values = _property_values(properties)
        project_id_text = _required_text(values, "ProjectId", entry_index=entry_index)
        project_code = _required_text(values, "ProjectCode", entry_index=entry_index)
        project_name = _required_text(values, "ProjectName", entry_index=entry_index)
        records.append(
            ODataProjectRecord(
                project_id=_parse_int32(project_id_text, "ProjectId", entry_index=entry_index),
                project_code=project_code,
                project_name=project_name,
                customer_id=_optional_text(values.get("CustomerID")),
                customer_name=_optional_text(values.get("CustomerName")),
                project_manager_id=_optional_text(values.get("ProjectManagerId")),
                project_manager_name=_optional_text(values.get("ProjectManagerName")),
                status=_optional_text(values.get("Status")),
                start_date=_parse_datetime(values.get("StartDate"), "StartDate", entry_index=entry_index),
                end_date=_parse_datetime(values.get("EndDate"), "EndDate", entry_index=entry_index),
                default_branch_code=_optional_text(values.get("DefaultBranchCode")),
                default_branch_description=_optional_text(values.get("DefaultBranchCode_Desc")),
                last_modified_at=_parse_datetime(
                    values.get("LastModifiedDateTime"),
                    "LastModifiedDateTime",
                    entry_index=entry_index,
                ),
                base_type=_optional_text(values.get("BaseType")),
            )
        )
    return tuple(records)


@dataclass(frozen=True, slots=True)
class ODataProjectSourceSettings:
    """Minimal RP_Projects OData settings; authentication is intentionally external."""

    base_url: str
    feed_path: str = "/oDATA/RP_Projects"
    timeout_seconds: float = 30.0

    def safe_summary(self) -> dict[str, object]:
        return {
            "protocol": "odata",
            "feed_path": self.feed_path,
        }


class ODataProjectSource(ProjectSourcePort):
    """Read-only RP_Projects source using an Atom/XML OData feed."""

    def __init__(
        self,
        settings: ODataProjectSourceSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        request_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        # Generic seam for #207B. 207A deliberately does not choose Basic, bearer,
        # OAuth or cookie/session authentication.
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
        # Never log URL/host, injected auth headers, exception details, response body,
        # or project data. Only stable contract metadata is emitted.
        logger.warning(
            "Acumatica OData project read failed kind=%s retryable=%s status=%s feed=%s reason=%s",
            failure_kind,
            retryable,
            http_status if http_status is not None else "-",
            self._settings.feed_path,
            reason or "-",
        )

    def list_projects(self) -> tuple[ExternalProjectRecord, ...]:
        headers = {
            "Accept": "application/atom+xml, application/xml;q=0.9",
            **self._request_headers,
        }
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._settings.timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = client.get(self._url(), headers=headers)
                response.raise_for_status()
                try:
                    parsed = parse_rp_projects_feed(response.content)
                except ODataProjectFeedError as exc:
                    self._log_failure(
                        failure_kind="invalid_payload",
                        retryable=False,
                        http_status=response.status_code,
                        reason=exc.reason,
                    )
                    raise ApplicationOperationError(
                        "La réponse OData Acumatica des projets est invalide.",
                        code="acumatica_project_response_invalid",
                        context=self._safe_context(
                            failure_kind="invalid_payload",
                            retryable=False,
                            http_status=response.status_code,
                            reason=exc.reason,
                            field=exc.field,
                            entry_index=exc.entry_index,
                        ),
                    ) from exc
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
                "Impossible de lire les projets depuis Acumatica.",
                code="acumatica_project_read_failed",
                context=self._safe_context(
                    failure_kind=failure_kind,
                    retryable=retryable,
                    http_status=status_code,
                ),
            ) from exc
        except httpx.TimeoutException as exc:
            self._log_failure(failure_kind="timeout", retryable=True)
            raise ApplicationOperationError(
                "Impossible de lire les projets depuis Acumatica.",
                code="acumatica_project_read_failed",
                context=self._safe_context(failure_kind="timeout", retryable=True),
            ) from exc
        except httpx.RequestError as exc:
            self._log_failure(failure_kind="network", retryable=True)
            raise ApplicationOperationError(
                "Impossible de lire les projets depuis Acumatica.",
                code="acumatica_project_read_failed",
                context=self._safe_context(failure_kind="network", retryable=True),
            ) from exc

        return tuple(record.to_external_record() for record in parsed)
