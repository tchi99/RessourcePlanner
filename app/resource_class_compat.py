from __future__ import annotations

from typing import Any

from . import v16


def install_resource_class_compat() -> None:
    """Prefer explicit installation wording over the generic automation keyword.

    Historical configuration labels such as ``Installation automatisation`` contain
    both terms. The older classifier tests the generic automation keyword first, so
    this narrow compatibility rule preserves the validated V1.8 classification until
    the classifier itself is moved into an explicit domain/read-model module.
    """
    if getattr(v16, "_resource_class_precedence_installed", False):
        return

    original_normalize = v16._normalize_resource_class

    def normalize_resource_class(value: Any) -> str | None:
        text = v16._normalized_text(value)
        if "installation" in text or "installateur" in text:
            return "Installation"
        return original_normalize(value)

    v16._normalize_resource_class = normalize_resource_class
    v16._resource_class_precedence_installed = True
