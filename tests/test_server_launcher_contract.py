from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ServerLauncherContractTests(unittest.TestCase):
    def test_local_sqlite_fallback_and_migration_are_guarded(self) -> None:
        launcher = (ROOT / "Lancer_Serveur.bat").read_text(encoding="utf-8")

        self.assertIn("if not defined RESOURCEPLANNER_DATABASE_URL", launcher)
        self.assertIn(
            'set "RESOURCEPLANNER_DATABASE_URL=sqlite:///./resourceplanner_server.db"',
            launcher,
        )
        self.assertIn('set "LOCAL_SQLITE_MODE=1"', launcher)
        self.assertIn('if "%LOCAL_SQLITE_MODE%"=="1"', launcher)
        self.assertIn('".venv\\Scripts\\python.exe" -m alembic upgrade head', launcher)
        self.assertIn('".venv\\Scripts\\python.exe" -m app.server', launcher)

    def test_existing_database_url_is_not_overwritten_unconditionally(self) -> None:
        launcher = (ROOT / "Lancer_Serveur.bat").read_text(encoding="utf-8")

        fallback_guard = launcher.index("if not defined RESOURCEPLANNER_DATABASE_URL")
        fallback_assignment = launcher.index(
            'set "RESOURCEPLANNER_DATABASE_URL=sqlite:///./resourceplanner_server.db"'
        )
        self.assertLess(fallback_guard, fallback_assignment)


if __name__ == "__main__":
    unittest.main()
