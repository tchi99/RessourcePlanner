from __future__ import annotations

import unittest

from tools.ci_change_classifier import classify_changes


class CiChangeClassifierTests(unittest.TestCase):
    def test_docs_and_process_only_stay_lightweight(self) -> None:
        result = classify_changes(["docs/CI_PATH_MATRIX.md", "AGENTS.md"])

        self.assertTrue(result.documentation_only)
        self.assertFalse(result.backend)
        self.assertFalse(result.frontend)
        self.assertFalse(result.runtime)
        self.assertFalse(result.conservative)

    def test_frontend_change_is_classified_without_python_backend(self) -> None:
        result = classify_changes(["docs/example.md", "frontend/src/App.tsx"])

        self.assertFalse(result.documentation_only)
        self.assertFalse(result.backend)
        self.assertTrue(result.frontend)
        self.assertFalse(result.runtime)
        self.assertFalse(result.conservative)

    def test_backend_change_is_classified(self) -> None:
        result = classify_changes(["app/server/api.py", "tests/test_api.py"])

        self.assertFalse(result.documentation_only)
        self.assertTrue(result.backend)
        self.assertFalse(result.frontend)
        self.assertFalse(result.runtime)
        self.assertFalse(result.conservative)

    def test_runtime_change_is_classified(self) -> None:
        result = classify_changes(["Dockerfile.backend", "deploy/synology/compose.yml"])

        self.assertFalse(result.documentation_only)
        self.assertFalse(result.backend)
        self.assertFalse(result.frontend)
        self.assertTrue(result.runtime)
        self.assertFalse(result.conservative)

    def test_ci_dependencies_and_tooling_are_conservative(self) -> None:
        for path in (
            ".github/workflows/syntax-check.yml",
            "requirements.txt",
            "constraints-ci.txt",
            "tools/run_test_shard.py",
            "dev-cockpit/package.json",
        ):
            with self.subTest(path=path):
                result = classify_changes([path])
                self.assertTrue(result.conservative)

    def test_unknown_path_is_fail_safe(self) -> None:
        result = classify_changes(["unexpected/new-runtime-file.conf"])

        self.assertFalse(result.documentation_only)
        self.assertTrue(result.conservative)

    def test_empty_change_set_is_fail_safe(self) -> None:
        result = classify_changes([])

        self.assertFalse(result.documentation_only)
        self.assertTrue(result.conservative)


if __name__ == "__main__":
    unittest.main()
