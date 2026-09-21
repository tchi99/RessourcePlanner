from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .communications import CommunicationTransportMessage
from .errors import (
    ApplicationError,
    ApplicationUnavailableError,
    ApplicationValidationError,
)


SMTP_SECURITY_STARTTLS = "STARTTLS"
SMTP_SECURITY_SSL_TLS = "SSL_TLS"
SMTP_SECURITY_MODES = (SMTP_SECURITY_STARTTLS, SMTP_SECURITY_SSL_TLS)


@dataclass(frozen=True, slots=True)
class SmtpTestLogEntry:
    level: str
    step: str
    message: str


@dataclass(frozen=True, slots=True)
class SmtpConnectionTestResult:
    ok: bool
    message: str
    log: tuple[SmtpTestLogEntry, ...]


@dataclass(frozen=True, slots=True)
class SmtpConfigurationStored:
    host: str | None
    port: int
    security: str
    username: str | None
    encrypted_password: str | None
    from_email: str | None
    from_name: str | None
    reply_to: str | None
    timeout_seconds: int
    enabled: bool
    updated_by: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SmtpConfigurationView:
    host: str | None
    port: int
    security: str
    username: str | None
    password_configured: bool
    from_email: str | None
    from_name: str | None
    reply_to: str | None
    timeout_seconds: int
    enabled: bool
    encryption_available: bool
    updated_by: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SmtpRuntimeConfiguration:
    host: str
    port: int
    security: str
    username: str | None
    credential: str | None
    from_email: str
    from_name: str | None
    reply_to: str | None
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class SmtpConfigurationUpdate:
    host: str
    port: int
    security: str
    username: str | None
    credential: str | None
    clear_password: bool
    from_email: str
    from_name: str | None
    reply_to: str | None
    timeout_seconds: int
    enabled: bool


class SmtpConfigurationRepositoryPort(Protocol):
    def get_smtp_configuration(self) -> SmtpConfigurationStored | None: ...

    def save_smtp_configuration(
        self,
        *,
        configuration: SmtpConfigurationStored,
        actor_name: str,
    ) -> SmtpConfigurationStored: ...


class SecretCipherPort(Protocol):
    def encrypt(self, value: str) -> str: ...

    def decrypt(self, value: str) -> str: ...


class SmtpClientPort(Protocol):
    def test_connection(
        self,
        configuration: SmtpRuntimeConfiguration,
    ) -> SmtpConnectionTestResult: ...

    def send_message(
        self,
        configuration: SmtpRuntimeConfiguration,
        message: CommunicationTransportMessage,
        *,
        message_id: str,
    ) -> str: ...


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _email(value: object, field: str, *, required: bool) -> str | None:
    text = _optional(value)
    if text is None:
        if required:
            raise ApplicationValidationError(
                f"{field} est requis.",
                code="smtp_configuration_required",
                context={"field": field},
            )
        return None
    if "@" not in text or text.startswith("@") or text.endswith("@"):
        raise ApplicationValidationError(
            f"{field} doit être une adresse courriel valide.",
            code="smtp_configuration_invalid_email",
            context={"field": field},
        )
    return text


class SmtpConfigurationService:
    def __init__(
        self,
        repository: SmtpConfigurationRepositoryPort,
        *,
        cipher: SecretCipherPort | None,
        client: SmtpClientPort,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._client = client

    def get(self) -> SmtpConfigurationView:
        row = self._repository.get_smtp_configuration()
        if row is None:
            row = SmtpConfigurationStored(
                host=None,
                port=587,
                security=SMTP_SECURITY_STARTTLS,
                username=None,
                encrypted_password=None,
                from_email=None,
                from_name=None,
                reply_to=None,
                timeout_seconds=20,
                enabled=False,
            )
        return SmtpConfigurationView(
            host=row.host,
            port=row.port,
            security=row.security,
            username=row.username,
            password_configured=bool(row.encrypted_password),
            from_email=row.from_email,
            from_name=row.from_name,
            reply_to=row.reply_to,
            timeout_seconds=row.timeout_seconds,
            enabled=row.enabled,
            encryption_available=self._cipher is not None,
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _validate_common(
        *,
        host: object,
        port: object,
        security: object,
        username: object,
        from_email: object,
        from_name: object,
        reply_to: object,
        timeout_seconds: object,
        enabled: bool,
    ) -> tuple[str, int, str, str | None, str, str | None, str | None, int]:
        host_value = _text(host)
        if not host_value:
            raise ApplicationValidationError(
                "Le serveur SMTP est requis.",
                code="smtp_configuration_required",
                context={"field": "host"},
            )
        try:
            port_value = int(port)
        except (TypeError, ValueError) as exc:
            raise ApplicationValidationError(
                "Le port SMTP doit être un entier.",
                code="smtp_configuration_invalid_port",
            ) from exc
        if not 1 <= port_value <= 65535:
            raise ApplicationValidationError(
                "Le port SMTP doit être compris entre 1 et 65535.",
                code="smtp_configuration_invalid_port",
            )
        security_value = _text(security).upper()
        if security_value not in SMTP_SECURITY_MODES:
            raise ApplicationValidationError(
                "Le mode SMTP doit être STARTTLS ou SSL_TLS.",
                code="smtp_configuration_invalid_security",
            )
        try:
            timeout_value = int(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ApplicationValidationError(
                "Le délai SMTP doit être un entier.",
                code="smtp_configuration_invalid_timeout",
            ) from exc
        if not 1 <= timeout_value <= 120:
            raise ApplicationValidationError(
                "Le délai SMTP doit être compris entre 1 et 120 secondes.",
                code="smtp_configuration_invalid_timeout",
            )
        return (
            host_value,
            port_value,
            security_value,
            _optional(username),
            _email(from_email, "from_email", required=True) or "",
            _optional(from_name),
            _email(reply_to, "reply_to", required=False),
            timeout_value,
        )

    def update(
        self,
        update: SmtpConfigurationUpdate,
        *,
        actor_name: str,
    ) -> SmtpConfigurationView:
        (
            host,
            port,
            security,
            username,
            from_email,
            from_name,
            reply_to,
            timeout_seconds,
        ) = self._validate_common(
            host=update.host,
            port=update.port,
            security=update.security,
            username=update.username,
            from_email=update.from_email,
            from_name=update.from_name,
            reply_to=update.reply_to,
            timeout_seconds=update.timeout_seconds,
            enabled=update.enabled,
        )
        current = self._repository.get_smtp_configuration()
        encrypted_password = (
            current.encrypted_password if current is not None else None
        )
        if update.clear_password:
            encrypted_password = None
        elif _text(update.credential):
            if self._cipher is None:
                raise ApplicationUnavailableError(
                    "La clé de chiffrement serveur n'est pas configurée.",
                    code="smtp_encryption_key_unavailable",
                )
            encrypted_password = self._cipher.encrypt(_text(update.credential))

        if username and not encrypted_password:
            raise ApplicationValidationError(
                "Un mot de passe SMTP est requis lorsqu'un nom d'utilisateur est configuré.",
                code="smtp_configuration_password_required",
            )

        stored = self._repository.save_smtp_configuration(
            configuration=SmtpConfigurationStored(
                host=host,
                port=port,
                security=security,
                username=username,
                encrypted_password=encrypted_password,
                from_email=from_email,
                from_name=from_name,
                reply_to=reply_to,
                timeout_seconds=timeout_seconds,
                enabled=bool(update.enabled),
            ),
            actor_name=actor_name,
        )
        return SmtpConfigurationView(
            host=stored.host,
            port=stored.port,
            security=stored.security,
            username=stored.username,
            password_configured=bool(stored.encrypted_password),
            from_email=stored.from_email,
            from_name=stored.from_name,
            reply_to=stored.reply_to,
            timeout_seconds=stored.timeout_seconds,
            enabled=stored.enabled,
            encryption_available=self._cipher is not None,
            updated_by=stored.updated_by,
            updated_at=stored.updated_at,
        )

    def runtime_configuration(
        self,
        *,
        require_enabled: bool,
    ) -> SmtpRuntimeConfiguration:
        row = self._repository.get_smtp_configuration()
        if row is None or not row.host or not row.from_email:
            raise ApplicationValidationError(
                "La configuration SMTP est incomplète.",
                code="smtp_configuration_incomplete",
            )
        if require_enabled and not row.enabled:
            raise ApplicationValidationError(
                "L'envoi SMTP est désactivé dans la configuration.",
                code="smtp_configuration_disabled",
            )
        credential_value = None
        if row.encrypted_password:
            if self._cipher is None:
                raise ApplicationUnavailableError(
                    "La clé de chiffrement serveur n'est pas configurée.",
                    code="smtp_encryption_key_unavailable",
                )
            try:
                credential_value = self._cipher.decrypt(row.encrypted_password)
            except Exception as exc:
                raise ApplicationUnavailableError(
                    "Le secret SMTP enregistré ne peut pas être déchiffré avec la clé serveur actuelle.",
                    code="smtp_secret_decryption_failed",
                ) from exc
        if row.username and not credential_value:
            raise ApplicationValidationError(
                "Le mot de passe SMTP est absent.",
                code="smtp_configuration_password_required",
            )
        return SmtpRuntimeConfiguration(
            host=row.host,
            port=row.port,
            security=row.security,
            username=row.username,
            credential=credential_value,
            from_email=row.from_email,
            from_name=row.from_name,
            reply_to=row.reply_to,
            timeout_seconds=row.timeout_seconds,
        )

    def test_connection(self) -> SmtpConnectionTestResult:
        try:
            configuration = self.runtime_configuration(require_enabled=False)
        except ApplicationError as exc:
            return SmtpConnectionTestResult(
                ok=False,
                message=exc.message,
                log=(
                    SmtpTestLogEntry(
                        level="ERROR",
                        step="configuration",
                        message=f"{exc.code}: {exc.message}",
                    ),
                ),
            )

        try:
            result = self._client.test_connection(configuration)
        except Exception as exc:
            return SmtpConnectionTestResult(
                ok=False,
                message="La connexion SMTP a échoué.",
                log=(
                    SmtpTestLogEntry(
                        level="ERROR",
                        step="client",
                        message=type(exc).__name__,
                    ),
                ),
            )

        if result.ok:
            return result
        return SmtpConnectionTestResult(
            ok=False,
            message=result.message or "La connexion SMTP a échoué.",
            log=result.log,
        )

    def send_message(
        self,
        message: CommunicationTransportMessage,
        *,
        message_id: str,
    ) -> str:
        configuration = self.runtime_configuration(require_enabled=True)
        try:
            return self._client.send_message(
                configuration,
                message,
                message_id=message_id,
            )
        except Exception as exc:
            raise ApplicationUnavailableError(
                "L'envoi SMTP du message a échoué.",
                code="smtp_delivery_failed",
                context={"reason": type(exc).__name__},
            ) from exc
