from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalPlanningRuntimeSyntaxTests(unittest.TestCase):
    def test_changed_runtime_modules_parse_as_python(self) -> None:
        for filename in (
            "operational_planning_runtime.py",
            "operational_planning_runtime_compat.py",
            "runtime_composition.py",
            "v171_performance.py",
        ):
            source = (APP / filename).read_text(encoding="utf-8")
            ast.parse(source, filename=filename)


if __name__ == "__main__":
    unittest.main()
