from __future__ import annotations


CONFIRMATION_TENTATIVE = "Tentative"
CONFIRMATION_CONFIRMED = "Confirmée"
VALID_CONFIRMATIONS = frozenset({CONFIRMATION_TENTATIVE, CONFIRMATION_CONFIRMED})


def _key(value: object) -> str:
    return str(value or "").strip().casefold()


def normalize_confirmation(
    value: object,
    *,
    default: str | None = None,
) -> str:
    """Return the canonical business confirmation value.

    The application historically used the feminine French label ``Confirmée`` for a
    request. Keep one canonical stored value at every level while accepting the common
    masculine/accentless spellings at input boundaries.
    """

    key = _key(value)
    if not key:
        if default is None:
            raise ValueError("Le statut de confirmation est requis.")
        return normalize_confirmation(default)

    if key == "tentative":
        return CONFIRMATION_TENTATIVE
    if key in {"confirmé", "confirme", "confirmée", "confirmee", "confirmed"}:
        return CONFIRMATION_CONFIRMED
    raise ValueError(
        "Statut de confirmation non supporté: "
        f"{value!s}. Valeurs permises: Tentative, Confirmée."
    )


def effective_confirmation(
    override: object,
    inherited: object,
    *,
    default: str = CONFIRMATION_CONFIRMED,
) -> str:
    """Resolve an optional lower-level override over its inherited snapshot."""

    if str(override or "").strip():
        return normalize_confirmation(override)
    return normalize_confirmation(inherited, default=default)
