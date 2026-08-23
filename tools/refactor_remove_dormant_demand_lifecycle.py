from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "app" / "ui.py"
SERVICE_UI_PATH = ROOT / "app" / "demand_service_ui.py"
TEST_PATH = ROOT / "tests" / "test_demand_service.py"

TARGET_METHODS = (
    "submit_request",
    "cancel_request",
    "open_approval_dialog",
    "open_correction_dialog",
)


def remove_class_methods(source: str) -> str:
    lines = source.splitlines(keepends=True)
    result: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        target = next(
            (
                name
                for name in TARGET_METHODS
                if line.startswith(f"    def {name}(")
            ),
            None,
        )
        if target is None:
            result.append(line)
            index += 1
            continue

        index += 1
        while index < len(lines):
            candidate = lines[index]
            if candidate.startswith("    def ") or candidate.startswith("    @"):
                break
            index += 1

    return "".join(result)


def update_ui() -> None:
    source = UI_PATH.read_text(encoding="utf-8")
    updated = remove_class_methods(source)

    for name in TARGET_METHODS:
        marker = f"    def {name}("
        if marker in updated:
            raise RuntimeError(f"Dormant lifecycle method still present: {name}")

    for direct_call in (
        "self.repo.submit_demand(",
        "self.repo.approve_demand(",
        "self.repo.request_correction(",
        "self.repo.update_demand(",
    ):
        if direct_call in updated:
            raise RuntimeError(f"Direct demand repository mutation still present: {direct_call}")

    UI_PATH.write_text(updated, encoding="utf-8")


def update_service_ui_docstring() -> None:
    source = SERVICE_UI_PATH.read_text(encoding="utf-8")
    old = '''    """Bind demand lifecycle actions to DemandService until pages are extracted.\n\n    The V1.x request page still lives on ``PlannerUI``. These explicit composition-time\n    bindings make submit/approve/correction/cancel cross the application-service\n    boundary now; tranche 4 can delete them when the request page/dialog becomes a\n    dedicated UI module.\n    """'''
    new = '''    """Install explicit demand lifecycle actions on the current request page.\n\n    ``PlannerUI`` no longer carries dormant V1.1 implementations of these actions.\n    Until the whole request page is extracted, this module is the sole UI owner of\n    submit/approve/correction/cancel and routes every mutation through ``DemandService``.\n    """'''
    if old not in source:
        raise RuntimeError("Expected demand_service_ui docstring was not found")
    SERVICE_UI_PATH.write_text(source.replace(old, new, 1), encoding="utf-8")


def update_tests() -> None:
    source = TEST_PATH.read_text(encoding="utf-8")
    test_name = "test_base_ui_no_longer_defines_dormant_demand_lifecycle"
    if test_name in source:
        return

    marker = '\n\nif __name__ == "__main__":\n'
    if marker not in source:
        raise RuntimeError("Could not locate unittest footer")

    addition = '''\n    def test_base_ui_no_longer_defines_dormant_demand_lifecycle(self) -> None:\n        root = Path(__file__).resolve().parents[1]\n        source = (root / "app" / "ui.py").read_text(encoding="utf-8")\n\n        for definition in (\n            "def submit_request(",\n            "def cancel_request(",\n            "def open_approval_dialog(",\n            "def open_correction_dialog(",\n        ):\n            self.assertNotIn(definition, source)\n\n        for direct_repository_call in (\n            "self.repo.submit_demand(",\n            "self.repo.approve_demand(",\n            "self.repo.request_correction(",\n            "self.repo.update_demand(",\n        ):\n            self.assertNotIn(direct_repository_call, source)\n\n        service_ui = (root / "app" / "demand_service_ui.py").read_text(encoding="utf-8")\n        for binding in (\n            "PlannerUI.submit_request = _submit_request_via_service",\n            "PlannerUI.cancel_request = _cancel_request_via_service",\n            "PlannerUI.open_approval_dialog = _open_approval_dialog_via_service",\n            "PlannerUI.open_correction_dialog = _open_correction_dialog_via_service",\n        ):\n            self.assertIn(binding, service_ui)\n'''
    TEST_PATH.write_text(source.replace(marker, addition + marker, 1), encoding="utf-8")


def main() -> None:
    update_ui()
    update_service_ui_docstring()
    update_tests()
    print("Dormant V1.1 demand lifecycle implementations removed.")


if __name__ == "__main__":
    main()
