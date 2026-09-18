from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any
from urllib.parse import quote

import httpx

from ...application import ApplicationOperationError, ExternalProjectRecord, ProjectSourcePort


logger = logging.getLogger(__name__)


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


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


@dataclass(frozen=True, slots=True)
class AcumaticaProjectSourceSettings:
    """Contract-based REST configuration without storing credentials in SQL."""

    base_url: str
    bearer_token: str = field(repr=False)
    endpoint: str = "Default"
    version: str = ""
    entity: str = "Project"
    number_field: str = "ProjectID"
    name_field: str = "Description"
    client_field: str = "Customer"
    project_manager_field: str = "ProjectManager"
    status_field: str = "Status"
    page_size: int = 200
    timeout_seconds: float = 30.0

    def safe_summary(self) -> dict[str, object]:
        return {
            "configured": True,
            "base_url": self.base_url.rstrip("/"),
            "endpoint": self.endpoint,
            "version": self.version,
            "entity": self.entity,
            "page_size": self.page_size,
        }


class AcumaticaProjectSource(ProjectSourcePort):
    """Read-only project source using Acumatica contract-based REST."""

    def __init__(
        self,
        settings: AcumaticaProjectSourceSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def _url(self) -> str:
        settings = self._settings
        return (
            f"{settings.base_url.rstrip('/')}"
            f"/entity/{quote(settings.endpoint, safe='')}"
            f"/{quote(settings.version, safe='')}"
            f"/{quote(settings.entity, safe='')}"
        )

    def _fields(self) -> tuple[str, ...]:
        settings = self._settings
        values = (
            settings.number_field,
            settings.name_field,
            settings.client_field,
            settings.project_manager_field,
            settings.status_field,
        )
        return tuple(dict.fromkeys(field for field in values if _text(field)))

    def _safe_context(
        self,
        *,
        failure_kind: str,
        retryable: bool,
        http_status: int | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        settings = self._settings
        context: dict[str, object] = {
            "endpoint": settings.endpoint,
            "entity": settings.entity,
            "failure_kind": failure_kind,
            "retryable": retryable,
        }
        if http_status is not None:
            context["http_status"] = int(http_status)
        if reason:
            context["reason"] = reason
        return context

    def _log_failure(
        self,
        *,
        failure_kind: str,
        retryable: bool,
        http_status: int | None = None,
    ) -> None:
        # Never log the URL, token, exception message, response body or business
        # payload. Endpoint/entity are contract metadata already exposed by the safe
        # runtime status route.
        logger.warning(
            "Acumatica project read failed kind=%s retryable=%s status=%s endpoint=%s entity=%s",
            failure_kind,
            retryable,
            http_status if http_status is not None else "-",
            self._settings.endpoint,
            self._settings.entity,
        )

    def _record(self, payload: dict[str, Any]) -> ExternalProjectRecord:
        settings = self._settings
        external_id = _text(payload.get("id"))
        number = _text(_unwrap(payload.get(settings.number_field)))
        name = _text(_unwrap(payload.get(settings.name_field)))
        if not external_id or not number or not name:
            raise ApplicationOperationError(
                "La réponse Acumatica contient un projet incomplet.",
                code="acumatica_project_payload_invalid",
                context={
                    "has_external_id": bool(external_id),
                    "has_number": bool(number),
                    "has_name": bool(name),
                },
            )

        return ExternalProjectRecord(
            external_id=external_id,
            number=number,
            name=name,
            client=_optional_text(_unwrap(payload.get(settings.client_field))),
            project_manager_name=_optional_text(
                _unwrap(payload.get(settings.project_manager_field))
            ),
            status=_text(_unwrap(payload.get(settings.status_field))) or "active",
        )

    def list_projects(self) -> tuple[ExternalProjectRecord, ...]:
        settings = self._settings
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {settings.bearer_token}",
        }
        page_size = max(int(settings.page_size or 0), 1)
        skip = 0
        result: list[ExternalProjectRecord] = []

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=settings.timeout_seconds,
                follow_redirects=True,
            ) as client:
                while True:
                    response = client.get(
                        self._url(),
                        headers=headers,
                        params={
                            "$select": ",".join(self._fields()),
                            "$top": str(page_size),
                            "$skip": str(skip),
                        },
                    )
                    response.raise_for_status()
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        self._log_failure(
                            failure_kind="invalid_json",
                            retryable=False,
                            http_status=response.status_code,
                        )
                        raise ApplicationOperationError(
                            "La réponse Acumatica des projets n'est pas un JSON valide.",
                            code="acumatica_project_response_invalid",
                            context=self._safe_context(
                                failure_kind="invalid_json",
                                retryable=False,
                                http_status=response.status_code,
                                reason="invalid_json",
                            ),
                        ) from exc

                    if not isinstance(payload, list):
                        self._log_failure(
                            failure_kind="invalid_payload",
                            retryable=False,
                            http_status=response.status_code,
                        )
                        raise ApplicationOperationError(
                            "La réponse Acumatica des projets n'est pas une liste.",
                            code="acumatica_project_response_invalid",
                            context=self._safe_context(
                                failure_kind="invalid_payload",
                                retryable=False,
                                http_status=response.status_code,
                                reason="not_a_list",
                            ),
                        )
                    rows = [row for row in payload if isinstance(row, dict)]
                    if len(rows) != len(payload):
                        self._log_failure(
                            failure_kind="invalid_payload",
                            retryable=False,
                            http_status=response.status_code,
                        )
                        raise ApplicationOperationError(
                            "La réponse Acumatica contient un projet au format invalide.",
                            code="acumatica_project_response_invalid",
                            context=self._safe_context(
                                failure_kind="invalid_payload",
                                retryable=False,
                                http_status=response.status_code,
                                reason="non_object_row",
                            ),
                        )

                    try:
                        parsed = [self._record(row) for row in rows]
                    except ApplicationOperationError as exc:
                        logger.warning(
                            "Acumatica project payload rejected code=%s endpoint=%s entity=%s",
                            exc.code,
                            settings.endpoint,
                            settings.entity,
                        )
                        raise
                    result.extend(parsed)
                    if len(rows) < page_size:
                        break
                    skip += page_size
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
                context=self._safe_context(
                    failure_kind="timeout",
                    retryable=True,
                ),
            ) from exc
        except httpx.RequestError as exc:
            self._log_failure(failure_kind="network", retryable=True)
            raise ApplicationOperationError(
                "Impossible de lire les projets depuis Acumatica.",
                code="acumatica_project_read_failed",
                context=self._safe_context(
                    failure_kind="network",
                    retryable=True,
                ),
            ) from exc
        except (TypeError, ValueError) as exc:
            self._log_failure(failure_kind="invalid_payload", retryable=False)
            raise ApplicationOperationError(
                "Impossible de lire les projets depuis Acumatica.",
                code="acumatica_project_read_failed",
                context=self._safe_context(
                    failure_kind="invalid_payload",
                    retryable=False,
                ),
            ) from exc

        return tuple(result)
