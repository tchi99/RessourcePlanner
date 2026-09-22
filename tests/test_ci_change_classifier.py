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

    def test_dev_cockpit_changes_do_not_request_primary_application_jobs(self) -> None:
        result = classify_changes(["dev-cockpit/frontend/src/App.tsx"])

        self.assertFalse(result.documentation_only)
        self.assertFalse(result.backend)
        self.assertFalse(result.frontend)
        self.assertFalse(result.runtime)
        self.assertFalse(result.conservative)

    def test_mixed_frontend_and_dev_cockpit_keeps_relevant_application_jobs(self) -> None:
        result = classify_changes([
            "frontend/src/App.tsx",
            "dev-cockpit/frontend/src/App.tsx",
        ])

        self.assertFalse(result.documentation_only)
        self.assertFalse(result.backend)
        self.assertTrue(result.frontend)
        self.assertFalse(result.runtime)
        self.assertFalse(result.conservative)

    def test_ci_dependencies_and_tooling_are_conservative(self) -> None:
        for path in (
            ".github/workflows/syntax-check.yml",
            ".github/workflows/dev-cockpit.yml",
            "requirements.txt",
            "constraints-ci.txt",
            "tools/run_test_shard.py",
        ):
            with self.subTest(path=path):
                result = classify_changes([path])
                self.assertTrue(result.conservative)

    def test_shared_runtime_files_keep_primary_application_validation(self) -> None:
        for path in ("docker-compose.yml", ".env.example"):
            with self.subTest(path=path):
                result = classify_changes([path])
                self.assertTrue(result.runtime)
                self.assertFalse(result.conservative)

    def test_workflow_path_filters_keep_dev_cockpit_required_check_lightweight(self) -> None:
        from pathlib import Path

        primary = Path(".github/workflows/syntax-check.yml").read_text(encoding="utf-8")
        cockpit = Path(".github/workflows/dev-cockpit.yml").read_text(encoding="utf-8")

        self.assertIn('      - "dev-cockpit/**"', primary)
        self.assertIn('      - "dev-cockpit/**"', cockpit)

        cockpit_only = classify_changes(["dev-cockpit/frontend/src/App.tsx"])
        self.assertFalse(cockpit_only.backend)
        self.assertFalse(cockpit_only.frontend)
        self.assertFalse(cockpit_only.runtime)
        self.assertFalse(cockpit_only.conservative)

        for shared_path in ("docker-compose.yml", ".env.example"):
            marker = f'      - "{shared_path}"'
            self.assertIn(marker, primary)
            self.assertIn(marker, cockpit)

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
