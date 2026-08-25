from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def _module_exists(base: Path, dotted: str) -> bool:
    target = base.joinpath(*dotted.split("."))
    return target.with_suffix(".py").exists() or (target / "__init__.py").exists()


class RelativeImportIntegrityTests(unittest.TestCase):
    def test_all_relative_app_imports_resolve_to_existing_modules(self) -> None:
        offenders: list[str] = []

        for path in APP.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            package_dir = path.parent

            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.level <= 0:
                    continue

                base = package_dir
                for _ in range(node.level - 1):
                    base = base.parent

                if node.module:
                    if not _module_exists(base, node.module):
                        offenders.append(
                            f"{path.relative_to(APP)}: from {'.' * node.level}{node.module} import ..."
                        )
                    continue

                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if not _module_exists(base, alias.name):
                        offenders.append(
                            f"{path.relative_to(APP)}: from {'.' * node.level} import {alias.name}"
                        )

        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
