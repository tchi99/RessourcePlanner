from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

import httpx


FailureMode = Literal["timeout", "network"]


@dataclass(frozen=True, slots=True)
class ODataMockRoute:
    """One synthetic GET response matched by path and a subset of query parameters."""

    query: Mapping[str, str] = field(default_factory=dict)
    path: str | None = None
    status_code: int = 200
    content: bytes = b""
    failure: FailureMode | None = None

    def matches(self, request: httpx.Request) -> bool:
        if request.method != "GET":
            return False
        if self.path is not None and request.url.path != self.path:
            return False
        return all(request.url.params.get(key) == value for key, value in self.query.items())


class ODataMockTransport:
    """Small reusable OData test double backed by httpx.MockTransport.

    It intentionally models only the request/response behavior RessourcePlanner
    adapters depend on. It is not an OData server implementation.
    """

    def __init__(self, *routes: ODataMockRoute) -> None:
        if not routes:
            raise ValueError("at least one OData mock route is required")
        self._routes = tuple(routes)
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for route in self._routes:
            if not route.matches(request):
                continue
            if route.failure == "timeout":
                raise httpx.ReadTimeout("synthetic OData timeout", request=request)
            if route.failure == "network":
                raise httpx.ConnectError("synthetic OData network error", request=request)
            return httpx.Response(
                route.status_code,
                content=route.content,
                request=request,
            )

        query_keys = ",".join(sorted(request.url.params.keys())) or "(none)"
        raise AssertionError(
            "Unexpected synthetic OData request "
            f"method={request.method} path={request.url.path} query_keys={query_keys}"
        )
