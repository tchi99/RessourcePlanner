from __future__ import annotations

import json
from typing import Any

from sqlalchemy import String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ...application import (
    ApplicationConflictError,
    ApplicationOperationError,
    CommandIdempotencyPort,
)
from ...application.idempotency import IdempotentAction
from .base import Base, TimestampMixin, new_id


class CommandIdempotencyReceipt(TimestampMixin, Base):
    """Durable result of one keyed API command.

    The actor/scope/key tuple is the business uniqueness boundary. Keeping the request
    fingerprint beside the serialized canonical response prevents a client from reusing
    one key for a different mutation.
    """

    __tablename__ = "command_idempotency_receipts"
    __table_args__ = (
        UniqueConstraint(
            "actor_name",
            "command_scope",
            "idempotency_key",
            name="uq_command_idempotency_actor_scope_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    command_scope: Mapped[str] = mapped_column(String(96), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)


class SqlCommandIdempotencyAdapter(CommandIdempotencyPort):
    """Replay keyed commands and make the receipt atomic with their SQL mutations."""

    def __init__(self, session: Session, *, actor_name: str = "api") -> None:
        self._session = session
        self._actor_name = str(actor_name or "api").strip() or "api"

    def _find(self, scope: str, key: str) -> CommandIdempotencyReceipt | None:
        return self._session.scalar(
            select(CommandIdempotencyReceipt).where(
                CommandIdempotencyReceipt.actor_name == self._actor_name,
                CommandIdempotencyReceipt.command_scope == scope,
                CommandIdempotencyReceipt.idempotency_key == key,
            )
        )

    @staticmethod
    def _replay(
        receipt: CommandIdempotencyReceipt,
        request_fingerprint: str,
    ) -> dict[str, Any]:
        if receipt.request_fingerprint != request_fingerprint:
            raise ApplicationConflictError(
                "Cette clé d'idempotence a déjà été utilisée avec un contenu différent.",
                code="idempotency_key_conflict",
                context={"command_scope": receipt.command_scope},
            )
        try:
            payload = json.loads(receipt.response_json)
        except (TypeError, ValueError) as exc:
            raise ApplicationOperationError(
                "Le résultat idempotent enregistré est illisible.",
                code="idempotency_receipt_invalid",
                context={"command_scope": receipt.command_scope},
            ) from exc
        if not isinstance(payload, dict):
            raise ApplicationOperationError(
                "Le résultat idempotent enregistré est invalide.",
                code="idempotency_receipt_invalid",
                context={"command_scope": receipt.command_scope},
            )
        return payload

    def replay_or_execute(
        self,
        *,
        scope: str,
        key: str,
        request_fingerprint: str,
        action: IdempotentAction,
    ) -> dict[str, Any]:
        command_scope = str(scope or "").strip()
        if not command_scope:
            raise ApplicationOperationError(
                "La portée de la commande idempotente est absente.",
                code="idempotency_scope_invalid",
            )

        existing = self._find(command_scope, key)
        if existing is not None:
            return self._replay(existing, request_fingerprint)

        try:
            # The SAVEPOINT includes both the business mutation and receipt insertion.
            # If another request wins the unique actor/scope/key race, SQL rolls this
            # attempt back to the savepoint before we replay the winner's result.
            with self._session.begin_nested():
                result = action()
                response_json = json.dumps(
                    result,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                self._session.add(
                    CommandIdempotencyReceipt(
                        actor_name=self._actor_name,
                        command_scope=command_scope,
                        idempotency_key=key,
                        request_fingerprint=request_fingerprint,
                        response_json=response_json,
                    )
                )
                self._session.flush()
            return result
        except IntegrityError as exc:
            # A concurrent request may have committed the same unique key while this
            # request was executing. The nested rollback keeps the outer request
            # transaction usable, so replay the winning receipt rather than returning a
            # duplicate business object.
            winner = self._find(command_scope, key)
            if winner is None:
                raise ApplicationOperationError(
                    "La commande idempotente n'a pas pu être enregistrée.",
                    code="idempotency_receipt_failed",
                    context={"command_scope": command_scope},
                ) from exc
            return self._replay(winner, request_fingerprint)
        except ApplicationConflictError:
            # A same-key concurrent command can lose a business CAS (notably the
            # global planning version) after the winner committed its mutation and
            # receipt. Once the SAVEPOINT has rolled this attempt back, prefer that
            # durable winner over surfacing a stale-version conflict.
            winner = self._find(command_scope, key)
            if winner is None:
                raise
            return self._replay(winner, request_fingerprint)
