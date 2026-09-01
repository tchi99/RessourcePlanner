from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalPlanningSortingSyntaxTests(unittest.TestCase):
    def test_sorting_runtime_sources_parse(self) -> None:
        for filename in (
            "operational_planning_sorting.py",
            "operational_planning_sorting_compat.py",
            "runtime_performance_compat.py",
            "runtime_composition.py",
        ):
            source = (APP / filename).read_text(encoding="utf-8")
            ast.parse(source, filename=filename)


if __name__ == "__main__":
    unittest.main()
