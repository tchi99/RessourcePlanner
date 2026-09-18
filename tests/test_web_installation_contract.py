from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WebInstallationContractTests(unittest.TestCase):
    def test_installer_uses_isolated_server_dependency_profile(self) -> None:
        installer = (ROOT / "Installer_Web.bat").read_text(encoding="utf-8")
        self.assertIn("pip install -r requirements-server.txt -c constraints-release.txt", installer)
        self.assertNotIn("requirements-legacy.txt", installer)
        self.assertIn(".venv-web", installer)
        self.assertIn("npm run build", installer)

        requirements = (ROOT / "requirements-server.txt").read_text(encoding="utf-8").casefold()
        for package in ("nicegui", "xlwings", "openpyxl"):
            self.assertNotIn(package, requirements)

    def test_launcher_runs_migrations_only_for_implicit_local_sqlite(self) -> None:
        launcher = (ROOT / "Lancer_Web.bat").read_text(encoding="utf-8")
        local_start = launcher.index('if "%LOCAL_SQLITE_MODE%"=="1" (')
        migration = launcher.index("-m alembic upgrade head")
        preflight = launcher.index("tools\\check_server_runtime.py")
        self.assertLess(local_start, migration)
        self.assertLess(migration, preflight)
        self.assertIn("RESOURCEPLANNER_FRONTEND_DIST", launcher)
        self.assertIn("/ready", launcher)

    def test_verifier_checks_installation_then_live_runtime(self) -> None:
        verifier = (ROOT / "Verifier_Web.bat").read_text(encoding="utf-8")
        install_check = verifier.index("tools\\check_installed_web.py")
        live_smoke = verifier.index("tools\\smoke_running_web.py")
        self.assertLess(install_check, live_smoke)
        self.assertIn("RESOURCEPLANNER_BASE_URL", verifier)


if __name__ == "__main__":
    unittest.main()
