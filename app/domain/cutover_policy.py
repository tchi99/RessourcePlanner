from __future__ import annotations


PURE_MODE = "pure"


def normalize_planning_engine_mode(value: object) -> str:
    """Compatibility shim for old local configurations.

    V1.8B is complete: the pure engine is now the only supported production engine.
    Historical ``legacy`` / ``guarded_pure`` values may still exist in an older local
    ``app_config.json`` but they are intentionally inert and normalize to ``pure``.
    New code should not use this function to select a runtime engine.
    """
    return PURE_MODE
