from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import json
from typing import Any, Protocol

from .errors import ApplicationValidationError


IDEMPOTENCY_KEY_MAX_LENGTH = 128
IdempotentAction = Callable[[], dict[str, Any]]


class CommandIdempotencyPort(Protocol):
    """Persist/replay one command result for a stable request fingerprint."""

    def replay_or_execute(
        self,
        *,
        scope: str,
        key: str,
        request_fingerprint: str,
        action: IdempotentAction,
    ) -> dict[str, Any]: ...


def normalize_idempotency_key(value: str | None) -> str | None:
    """Normalize an optional API key without making idempotency mandatory yet."""

    if value is None:
        return None
    key = str(value).strip()
    if not key:
        raise ApplicationValidationError(
            "La clé d'idempotence ne peut pas être vide.",
            code="idempotency_key_invalid",
        )
    if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise ApplicationValidationError(
            f"La clé d'idempotence ne peut pas dépasser {IDEMPOTENCY_KEY_MAX_LENGTH} caractères.",
            code="idempotency_key_invalid",
            context={"max_length": IDEMPOTENCY_KEY_MAX_LENGTH},
        )
    return key


def request_fingerprint(payload: Mapping[str, Any]) -> str:
    """Return a deterministic SHA-256 over the canonical command input."""

    canonical = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotentCommandExecutor:
    """Application service that makes an optional command key durable through a port."""

    def __init__(self, port: CommandIdempotencyPort) -> None:
        self._port = port

    def execute(
        self,
        *,
        scope: str,
        key: str | None,
        request_payload: Mapping[str, Any],
        action: IdempotentAction,
    ) -> dict[str, Any]:
        normalized_key = normalize_idempotency_key(key)
        if normalized_key is None:
            return action()
        return self._port.replay_or_execute(
            scope=str(scope).strip(),
            key=normalized_key,
            request_fingerprint=request_fingerprint(request_payload),
            action=action,
        )
