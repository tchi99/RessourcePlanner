from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


Installer = Callable[[], None]


@dataclass(frozen=True)
class CompositionStep:
    """One explicit application-composition step.

    The current V1.x application still contains historical installers which mutate
    classes/modules at runtime. Keeping their order in one manifest makes that
    transitional dependency visible and testable while each feature is progressively
    moved to explicit services/pages.
    """

    name: str
    category: str


@dataclass(frozen=True)
class RuntimeCompositionReport:
    installed_steps: tuple[str, ...]


RUNTIME_COMPOSITION_MANIFEST: tuple[CompositionStep, ...] = (
    CompositionStep("nicegui_compat", "compatibility"),
    CompositionStep("runtime_optimizations", "core"),
    CompositionStep("features", "legacy"),
    CompositionStep("bugfixes", "legacy"),
    CompositionStep("v13_features", "legacy"),
    CompositionStep("v13_fixes", "legacy"),
    CompositionStep("v14_features", "legacy"),
    CompositionStep("v14_fixes", "legacy"),
    CompositionStep("v15_features", "legacy"),
    CompositionStep("v15_refinements", "legacy"),
    CompositionStep("v16_features", "legacy"),
    CompositionStep("v16_refinements", "legacy"),
    CompositionStep("operational_planning_runtime", "compatibility"),
    CompositionStep("resource_management", "compatibility"),
    CompositionStep("operational_planning_sorting", "compatibility"),
    CompositionStep("runtime_performance", "compatibility"),
    CompositionStep("resource_local_preferences", "compatibility"),
    CompositionStep("v18_features", "legacy"),
    CompositionStep("effort_identity_guard", "compatibility"),
    CompositionStep("v18_refinements", "legacy"),
    CompositionStep("quick_shift_ui", "application"),
    CompositionStep("operational_planning_compat", "compatibility"),
    CompositionStep("resource_class_compat", "compatibility"),
    CompositionStep("location_projection", "compatibility"),
    CompositionStep("operational_planning_page", "application"),
    CompositionStep("demand_editor_ui", "application"),
    CompositionStep("planning_service_ui", "application"),
    CompositionStep("allocation_service_ui", "application"),
    CompositionStep("pure_validation_ui", "application"),
    CompositionStep("communication_ui", "communications"),
    CompositionStep("communication_obsolescence", "communications"),
    CompositionStep("communication_outlook", "communications"),
    CompositionStep("communication_mail_clients", "communications"),
    CompositionStep("thunderbird_setup", "communications"),
)


def composition_manifest() -> tuple[CompositionStep, ...]:
    return RUNTIME_COMPOSITION_MANIFEST


def _runtime_installers() -> tuple[tuple[str, Installer], ...]:
    from .allocation_service_ui import install_allocation_service_ui
    from .bugfixes import install_bugfixes
    from .communication_mail_clients_ui import install_communication_mail_clients_ui
    from .communication_obsolescence_ui import install_communication_obsolescence_guard
    from .communication_outlook_ui import install_communication_outlook_ui
    from .communication_thunderbird_setup_fix import install_thunderbird_setup_fix
    from .communication_ui import install_communication_ui
    from .demand_editor_ui import install_demand_editor_ui
    from .effort_identity_guard import install_effort_identity_guard
    from .features import install_features
    from .features_runtime import apply_runtime_optimizations
    from .location_projection import install_location_projection
    from .operational_planning_compat import install_operational_planning_compat
    from .operational_planning_page import install_operational_planning_page
    from .operational_planning_runtime_compat import (
        install_operational_planning_runtime_compat,
    )
    from .operational_planning_sorting_compat import install_operational_planning_sorting
    from .planning_service_ui import install_planning_service_ui
    from .pure_validation_ui import install_pure_validation_ui
    from .quick_shift_ui import install_quick_shift_ui
    from .resource_class_compat import install_resource_class_compat
    from .resource_local_preferences import install_resource_local_preferences
    from .resource_management_compat import install_resource_management_compat
    from .runtime_performance_compat import install_runtime_performance_compat
    from .v13 import install_v13_features
    from .v13_fixes import install_v13_fixes
    from .v14 import install_v14_features
    from .v14_fixes import install_v14_fixes
    from .v15 import install_v15_features
    from .v15_refinements import install_v15_refinements
    from .v16 import install_v16_features
    from .v16_refinements import install_v16_refinements
    from .v18 import install_v18_features
    from .v18_refinements import install_v18_refinements

    return (
        ("runtime_optimizations", apply_runtime_optimizations),
        ("features", install_features),
        ("bugfixes", install_bugfixes),
        ("v13_features", install_v13_features),
        ("v13_fixes", install_v13_fixes),
        ("v14_features", install_v14_features),
        ("v14_fixes", install_v14_fixes),
        ("v15_features", install_v15_features),
        ("v15_refinements", install_v15_refinements),
        ("v16_features", install_v16_features),
        ("v16_refinements", install_v16_refinements),
        ("operational_planning_runtime", install_operational_planning_runtime_compat),
        ("resource_management", install_resource_management_compat),
        ("operational_planning_sorting", install_operational_planning_sorting),
        ("runtime_performance", install_runtime_performance_compat),
        ("resource_local_preferences", install_resource_local_preferences),
        ("v18_features", install_v18_features),
        ("effort_identity_guard", install_effort_identity_guard),
        ("v18_refinements", install_v18_refinements),
        ("quick_shift_ui", install_quick_shift_ui),
        ("operational_planning_compat", install_operational_planning_compat),
        ("resource_class_compat", install_resource_class_compat),
        ("location_projection", install_location_projection),
        ("operational_planning_page", install_operational_planning_page),
        ("demand_editor_ui", install_demand_editor_ui),
        ("planning_service_ui", install_planning_service_ui),
        ("allocation_service_ui", install_allocation_service_ui),
        ("pure_validation_ui", install_pure_validation_ui),
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
    """Install the transitional V1 runtime in one explicit, audited order."""
    from .v172_nicegui_compat import install_v172_nicegui_compat

    install_v172_nicegui_compat()
    installers = _runtime_installers()
    _validate_installer_order(installers)

    installed = ["nicegui_compat"]
    for name, installer in installers:
        installer()
        installed.append(name)
    return RuntimeCompositionReport(installed_steps=tuple(installed))


def install_planning_engine() -> str:
    """Install the sole authoritative pure engine after transitional installers."""
    from .planning_cutover import install_planning_engine as install_authoritative_engine

    return install_authoritative_engine()
