from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from fastapi import FastAPI, Request


FRAME_ANCESTORS_ENV = "RESOURCEPLANNER_FRAME_ANCESTORS"
OIDC_COOKIE_SAMESITE_ENV = "RESOURCEPLANNER_OIDC_COOKIE_SAMESITE"

_ALLOWED_SAMESITE = {"lax", "strict", "none"}
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _frame_source(value: str) -> str:
    source = value.strip()
    if source in {"'none'", "'self'"}:
        return source
    if "*" in source:
        raise ValueError(f"{FRAME_ANCESTORS_ENV} n'accepte pas de wildcard.")

    parsed = urlsplit(source)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(
            f"{FRAME_ANCESTORS_ENV} accepte uniquement 'self', 'none' ou des origines HTTPS explicites."
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"Origine invalide dans {FRAME_ANCESTORS_ENV}: {source}")
    if parsed.path not in {"", "/"}:
        raise ValueError(
            f"{FRAME_ANCESTORS_ENV} attend une origine sans chemin: {source}"
        )
    host = parsed.hostname.casefold()
    if parsed.scheme.casefold() != "https" and not (
        parsed.scheme.casefold() == "http" and host in _LOOPBACK_HOSTS
    ):
        raise ValueError(
            f"{FRAME_ANCESTORS_ENV} exige HTTPS hors localhost: {source}"
        )

    port = f":{parsed.port}" if parsed.port is not None else ""
    hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"{parsed.scheme.casefold()}://{hostname}{port}"


def parse_frame_ancestors(value: object) -> tuple[str, ...]:
    text = _text(value)
    if not text:
        return ("'none'",)

    parts = tuple(part for part in re.split(r"[\s,]+", text) if part)
    sources = tuple(dict.fromkeys(_frame_source(part) for part in parts))
    if "'none'" in sources and len(sources) != 1:
        raise ValueError(
            f"{FRAME_ANCESTORS_ENV}: 'none' doit être utilisé seul."
        )
    return sources or ("'none'",)


def parse_cookie_samesite(value: object, *, secure_cookie: bool) -> str:
    mode = (_text(value) or "lax").casefold()
    if mode not in _ALLOWED_SAMESITE:
        allowed = ", ".join(sorted(_ALLOWED_SAMESITE))
        raise ValueError(
            f"{OIDC_COOKIE_SAMESITE_ENV} doit être l'une des valeurs suivantes: {allowed}."
        )
    if mode == "none" and not secure_cookie:
        raise ValueError(
            f"{OIDC_COOKIE_SAMESITE_ENV}=none exige RESOURCEPLANNER_OIDC_SECURE_COOKIE=true."
        )
    return mode


@dataclass(frozen=True, slots=True)
class EmbeddingSettings:
    frame_ancestors: tuple[str, ...] = ("'none'",)
    oidc_cookie_samesite: str = "lax"

    @property
    def frame_ancestors_directive(self) -> str:
        return "frame-ancestors " + " ".join(self.frame_ancestors)

    @classmethod
    def from_environment(
        cls,
        values: Mapping[str, str],
        *,
        secure_cookie: bool,
    ) -> "EmbeddingSettings":
        return cls(
            frame_ancestors=parse_frame_ancestors(values.get(FRAME_ANCESTORS_ENV)),
            oidc_cookie_samesite=parse_cookie_samesite(
                values.get(OIDC_COOKIE_SAMESITE_ENV),
                secure_cookie=secure_cookie,
            ),
        )


def install_embedding_headers(app: FastAPI, settings: EmbeddingSettings) -> None:
    directive = settings.frame_ancestors_directive

    @app.middleware("http")
    async def add_embedding_policy(request: Request, call_next):
        response = await call_next(request)
        current = str(response.headers.get("Content-Security-Policy") or "").strip()
        if current:
            response.headers["Content-Security-Policy"] = current.rstrip("; ") + "; " + directive
        else:
            response.headers["Content-Security-Policy"] = directive
        return response
