from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


Installer = Callable[[], None]


@dataclass(frozen=True)
class CompositionStep:
    """One explicit application-composition step.

    The current V1.x application still contains historical installers which mutate
    classes/modules at runtime.  Keeping their order in one manifest makes that
    transitional dependency visible and testable while each feature is progressively
    moved to explicit services/pages.
    """

    name: str
    category: str


@dataclass(frozen=True)
class RuntimeCompositionReport:
    installed_steps: tuple[str, ...]


# This manifest is intentionally data-only: importing this module does not import the
# historical feature modules and therefore cannot mutate NiceGUI/PlannerUI by itself.
RUNTIME_COMPOSITION_MANIFEST: tuple[CompositionStep, ...] = (
    CompositionStep("nicegui_compat", "compatibility"),
    CompositionStep("runtime_optimizations", "core"),
    CompositionStep("features", "legacy"),
    CompositionStep("bugfixes", "legacy"),
    CompositionStep("v13_features", "legacy"),
    CompositionStep("v13_fixes", "legacy"),
    CompositionStep("v14_features", "legacy"),
    CompositionStep("v14_fixes", "legacy"),
    CompositionStep("v14_runtime", "legacy"),
    CompositionStep("v15_features", "legacy"),
    CompositionStep("v15_refinements", "legacy"),
    CompositionStep("v16_features", "legacy"),
    CompositionStep("v16_refinements", "legacy"),
    CompositionStep("v17_features", "legacy"),
    CompositionStep("v17_refinements", "legacy"),
    CompositionStep("v17_sort_fix", "legacy"),
    CompositionStep("v171_performance", "legacy"),
    CompositionStep("v171_local_preferences", "legacy"),
    CompositionStep("v18_features", "legacy"),
    CompositionStep("v18_fixes", "legacy"),
    CompositionStep("v18_refinements", "legacy"),
    CompositionStep("v18_single_scroll", "legacy"),
    CompositionStep("v18_calendar_sizing", "legacy"),
    CompositionStep("v18_workflow_fixes", "legacy"),
    CompositionStep("demand_legacy_cleanup", "compatibility"),
    CompositionStep("planning_service_ui", "application"),
    CompositionStep("demand_service_ui", "application"),
    CompositionStep("communication_ui", "communications"),
    CompositionStep("communication_obsolescence", "communications"),
    CompositionStep("communication_outlook", "communications"),
    CompositionStep("communication_mail_clients", "communications"),
    CompositionStep("thunderbird_setup", "communications"),
)


def composition_manifest() -> tuple[CompositionStep, ...]:
    """Return the declared startup composition without triggering installers."""

    return RUNTIME_COMPOSITION_MANIFEST


def _runtime_installers() -> tuple[tuple[str, Installer], ...]:
    """Resolve installers lazily after the NiceGUI compatibility shim is active."""

    from .bugfixes import install_bugfixes
    from .communication_mail_clients_ui import install_communication_mail_clients_ui
    from .communication_obsolescence_ui import install_communication_obsolescence_guard
    from .communication_outlook_ui import install_communication_outlook_ui
    from .communication_thunderbird_setup_fix import install_thunderbird_setup_fix
    from .communication_ui import install_communication_ui
    from .demand_legacy_cleanup import install_demand_legacy_cleanup
    from .demand_service_ui import install_demand_service_ui
    from .features import install_features
    from .features_runtime import apply_runtime_optimizations
    from .planning_service_ui import install_planning_service_ui
    from .v13 import install_v13_features
    from .v13_fixes import install_v13_fixes
    from .v14 import install_v14_features
    from .v14_fixes import install_v14_fixes
    from .v14_runtime import install_v14_runtime
    from .v15 import install_v15_features
    from .v15_refinements import install_v15_refinements
    from .v16 import install_v16_features
    from .v16_refinements import install_v16_refinements
    from .v17 import install_v17_features
    from .v17_refinements import install_v17_refinements
    from .v17_sort_fix import install_v17_sort_fix
    from .v171_local_preferences import install_v171_local_preferences
    from .v171_performance import install_v171_performance
    from .v18 import install_v18_features
    from .v18_calendar_sizing import install_v18_calendar_sizing
    from .v18_fixes import install_v18_fixes
    from .v18_refinements import install_v18_refinements
    from .v18_single_scroll import install_v18_single_scroll
    from .v18_workflow_fixes import install_v18_workflow_fixes

    return (
        ("runtime_optimizations", apply_runtime_optimizations),
        ("features", install_features),
        ("bugfixes", install_bugfixes),
        ("v13_features", install_v13_features),
        ("v13_fixes", install_v13_fixes),
        ("v14_features", install_v14_features),
        ("v14_fixes", install_v14_fixes),
        ("v14_runtime", install_v14_runtime),
        ("v15_features", install_v15_features),
        ("v15_refinements", install_v15_refinements),
        ("v16_features", install_v16_features),
        ("v16_refinements", install_v16_refinements),
        ("v17_features", install_v17_features),
        ("v17_refinements", install_v17_refinements),
        ("v17_sort_fix", install_v17_sort_fix),
        ("v171_performance", install_v171_performance),
        ("v171_local_preferences", install_v171_local_preferences),
        ("v18_features", install_v18_features),
        ("v18_fixes", install_v18_fixes),
        ("v18_refinements", install_v18_refinements),
        ("v18_single_scroll", install_v18_single_scroll),
        ("v18_calendar_sizing", install_v18_calendar_sizing),
        ("v18_workflow_fixes", install_v18_workflow_fixes),
        ("demand_legacy_cleanup", install_demand_legacy_cleanup),
        ("planning_service_ui", install_planning_service_ui),
        ("demand_service_ui", install_demand_service_ui),
        ("communication_ui", install_communication_ui),
        ("communication_obsolescence", install_communication_obsolescence_guard),
        ("communication_outlook", install_communication_outlook_ui),
        ("communication_mail_clients", install_communication_mail_clients_ui),
        ("thunderbird_setup", install_thunderbird_setup_fix),
    )


def _validate_installer_order(installers: Iterable[tuple[str, Installer]]) -> None:
    actual = ("nicegui_compat", *(name for name, _installer in installers))
    expected = tuple(step.name for step in RUNTIME_COMPOSITION_MANIFEST)
    if actual != expected:
        raise RuntimeError(
            "Runtime composition no longer matches the declared manifest. "
            "Update the manifest and tests explicitly instead of relying on import order."
        )


def install_runtime_features() -> RuntimeCompositionReport:
    """Install the transitional V1 runtime in one explicit, audited order.

    This function does not pretend the historical monkey-patches are already gone.
    Instead it creates one composition root so future refactors can replace individual
    legacy steps with explicit services/pages without modifying ``main.py`` or relying
    on scattered import side effects.
    """

    # Must run before importing historical modules which may call global NiceGUI head/
    # body helpers during their own installation.
    from .v172_nicegui_compat import install_v172_nicegui_compat

    install_v172_nicegui_compat()
    installers = _runtime_installers()
    _validate_installer_order(installers)

    installed = ["nicegui_compat"]
    for name, installer in installers:
        installer()
        installed.append(name)
    return RuntimeCompositionReport(installed_steps=tuple(installed))


def install_planning_engine(mode: object) -> str:
    """Install the selected planning engine after all transitional feature installers."""

    from .planning_cutover import install_planning_cutover

    return install_planning_cutover(mode)
