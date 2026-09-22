from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Iterable


DOCUMENTATION_PROCESS_PATTERNS = (
    "docs/**",
    "AGENTS.md",
)

BACKEND_PATTERNS = (
    "app/**",
    "tests/**",
    "migrations/**",
    "main.py",
    "alembic.ini",
)

FRONTEND_PATTERNS = (
    "frontend/**",
)

RUNTIME_PATTERNS = (
    "Dockerfile.backend",
    "docker-compose.yml",
    ".dockerignore",
    ".env.example",
    "deploy/**",
    "Lancer_Application.bat",
    "Lancer_Application_Legacy.bat",
    "Installer.bat",
    "Installer_Web.bat",
    "Lancer_Serveur.bat",
    "Lancer_Web.bat",
    "Verifier_Web.bat",
    "Charger_Donnees_Demo.bat",
)

CONSERVATIVE_PATTERNS = (
    ".github/workflows/**",
    "requirements*.txt",
    "constraints*.txt",
    "tools/**",
    "dev-cockpit/**",
)


@dataclass(frozen=True)
class CiChangeClassification:
    documentation_only: bool
    backend: bool
    frontend: bool
    runtime: bool
    conservative: bool

    def github_outputs(self) -> dict[str, bool]:
        return {
            "documentation_only": self.documentation_only,
            "backend": self.backend,
            "frontend": self.frontend,
            "runtime": self.runtime,
            "conservative": self.conservative,
        }


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def classify_changes(paths: Iterable[str]) -> CiChangeClassification:
    changed_paths = tuple(path.strip() for path in paths if path.strip())
    if not changed_paths:
        return CiChangeClassification(
            documentation_only=False,
            backend=False,
            frontend=False,
            runtime=False,
            conservative=True,
        )

    documentation_only = True
    backend = False
    frontend = False
    runtime = False
    conservative = False

    for path in changed_paths:
        if _matches(path, DOCUMENTATION_PROCESS_PATTERNS):
            continue

        documentation_only = False
        if _matches(path, BACKEND_PATTERNS):
            backend = True
        elif _matches(path, FRONTEND_PATTERNS):
            frontend = True
        elif _matches(path, RUNTIME_PATTERNS):
            runtime = True
        elif _matches(path, CONSERVATIVE_PATTERNS):
            conservative = True
        else:
            conservative = True

    return CiChangeClassification(
        documentation_only=documentation_only,
        backend=backend,
        frontend=frontend,
        runtime=runtime,
        conservative=conservative,
    )


def main() -> int:
    classification = classify_changes(line.rstrip("\n") for line in __import__("sys").stdin)
    for key, value in classification.github_outputs().items():
        print(f"{key}={str(value).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
