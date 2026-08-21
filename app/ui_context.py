from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, Mapping


class ScopedNiceGUI:
    """Module-local facade for context-scoped NiceGUI factory overrides.

    A few historical renderers temporarily assign to ``module.ui.select`` while
    rendering.  When ``module.ui`` points directly at ``nicegui.ui`` that assignment
    mutates a process-wide factory and can leak across concurrent clients.  This
    facade keeps those transitional assignments local to a ``ContextVar`` while all
    unaffected attributes continue to delegate to the real NiceGUI module.

    Static overrides are useful for legacy components which should permanently use a
    different factory, such as the operational planning horizontal scroll container.
    """

    _ressourceplanner_scoped_ui = True

    def __init__(
        self,
        delegate: Any,
        *,
        scope_name: str,
        scoped_factories: tuple[str, ...] = ("select",),
        static_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "_delegate", delegate)
        object.__setattr__(self, "_static_overrides", dict(static_overrides or {}))
        object.__setattr__(
            self,
            "_scoped_overrides",
            {
                name: ContextVar(
                    f"ressourceplanner_ui_{scope_name}_{name}",
                    default=None,
                )
                for name in scoped_factories
            },
        )

    @property
    def delegate(self) -> Any:
        return object.__getattribute__(self, "_delegate")

    def base_factory(self, name: str) -> Any:
        """Return the underlying NiceGUI factory, bypassing scoped/static overrides."""

        return getattr(self.delegate, name)

    def __getattr__(self, name: str) -> Any:
        static = object.__getattribute__(self, "_static_overrides")
        if name in static:
            return static[name]

        scoped = object.__getattribute__(self, "_scoped_overrides")
        variable = scoped.get(name)
        if variable is not None:
            value = variable.get()
            if value is not None:
                return value

        return getattr(self.delegate, name)

    def __setattr__(self, name: str, value: Any) -> None:
        scoped = object.__getattribute__(self, "_scoped_overrides")
        variable = scoped.get(name)
        if variable is not None:
            base = getattr(self.delegate, name)
            variable.set(None if value is base else value)
            return
        object.__setattr__(self, name, value)

    def set_static_override(self, name: str, value: Any) -> None:
        object.__getattribute__(self, "_static_overrides")[name] = value

    @contextmanager
    def override_factory(self, name: str, value: Callable[..., Any]) -> Iterator[None]:
        scoped = object.__getattribute__(self, "_scoped_overrides")
        if name not in scoped:
            raise KeyError(f"Factory {name!r} is not configured as context-scoped")
        token = scoped[name].set(value)
        try:
            yield
        finally:
            scoped[name].reset(token)


def ensure_scoped_ui(
    module: Any,
    *,
    scope_name: str,
    scoped_factories: tuple[str, ...] = ("select",),
    static_overrides: Mapping[str, Any] | None = None,
) -> ScopedNiceGUI:
    """Install/reuse a module-local facade without touching global ``nicegui.ui``."""

    current = module.ui
    if isinstance(current, ScopedNiceGUI):
        facade = current
        for name, value in (static_overrides or {}).items():
            facade.set_static_override(name, value)
        return facade

    facade = ScopedNiceGUI(
        current,
        scope_name=scope_name,
        scoped_factories=scoped_factories,
        static_overrides=static_overrides,
    )
    module.ui = facade
    return facade
