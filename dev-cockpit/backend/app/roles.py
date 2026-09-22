from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from threading import Lock
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


AvatarPreset = Literal["product-owner", "developer", "architect", "reviewer", "generic"]
ROLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class RoleConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    avatar: AvatarPreset = "generic"
    chat_url: str = Field(default="", max_length=2048)
    enabled: bool = True
    order: int = Field(default=0, ge=0, le=999)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not ROLE_ID_RE.fullmatch(normalized):
            raise ValueError(
                "id doit contenir seulement lettres minuscules, chiffres, tirets ou underscores."
            )
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name ne peut pas être vide.")
        return normalized

    @field_validator("chat_url")
    @classmethod
    def validate_chat_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("chat_url doit être une URL http(s) valide.")
        return normalized


class RolesConfig(BaseModel):
    roles: list[RoleConfig] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "RolesConfig":
        ids = [role.id for role in self.roles]
        if len(ids) != len(set(ids)):
            raise ValueError("Chaque rôle doit avoir un id unique.")
        return self


DEFAULT_ROLES = RolesConfig(
    roles=[
        RoleConfig(
            id="product-owner",
            name="Product Owner",
            avatar="product-owner",
            enabled=True,
            order=10,
        ),
        RoleConfig(
            id="developer",
            name="Developer",
            avatar="developer",
            enabled=True,
            order=20,
        ),
        RoleConfig(
            id="architect",
            name="Architecte",
            avatar="architect",
            enabled=True,
            order=30,
        ),
    ]
)


class RoleStore:
    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / "roles.json"
        self._lock = Lock()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> RolesConfig:
        with self._lock:
            if not self._path.exists():
                return DEFAULT_ROLES.model_copy(deep=True)
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                return RolesConfig.model_validate(raw)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise RuntimeError(
                    f"Configuration des rôles invalide dans {self._path}."
                ) from exc

    def save(self, config: RolesConfig) -> RolesConfig:
        normalized = RolesConfig(
            roles=sorted(
                [role.model_copy(deep=True) for role in config.roles],
                key=lambda role: (role.order, role.name.lower(), role.id),
            )
        )
        payload = json.dumps(
            normalized.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ) + "\n"

        with self._lock:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._data_dir,
                    prefix=".roles-",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                    temporary_path = Path(handle.name)
                os.replace(temporary_path, self._path)
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink(missing_ok=True)

        return normalized
