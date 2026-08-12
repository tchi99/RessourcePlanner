from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini",
    ".cfg", ".bat", ".ps1", ".sh", ".csv", ".tsv", ".html", ".css", ".js",
}
SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", "node_modules",
}
LOCAL_STATE_FILES = {
    "app_config.json",
    "user_preferences.json",
    "user_preferences.json.tmp",
    ".privacy_terms.local",
}
PLACEHOLDER_USERNAMES = {
    "utilisateur", "votrenom", "user", "username", "example", "demo", "test", "...",
}
SCANNER_PATH = "tools/privacy_scan.py"


@dataclass(frozen=True)
class Finding:
    category: str
    path: str
    line: int


PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "email",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    ),
    (
        "phone",
        re.compile(
            r"(?<!\d)(?:\+?1[ .-]?)?(?:\([2-9]\d{2}\)|[2-9]\d{2})[ .-]\d{3}[ .-]\d{4}(?!\d)"
        ),
    ),
    (
        "canadian_postal_code",
        re.compile(
            r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d\b",
            re.IGNORECASE,
        ),
    ),
    (
        "street_address",
        re.compile(
            r"\b\d{1,6}\s+[^,\n]{2,60}\b(?:Rue|Street|St\.?|Avenue|Ave\.?|Boulevard|Boul\.?|Road|Rd\.?|Chemin|Ch\.?|Drive|Dr\.?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "private_ip",
        re.compile(
            r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
        ),
    ),
    (
        "unc_path",
        re.compile(r"\\\\" + r"[^\\\s]+" + r"\\" + r"[^\\\s]+"),
    ),
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|api[_-]?key|secret|access[_-]?token|client[_-]?secret)\b\s*[:=]\s*['\"]?([^'\"\s,}]+)"
        ),
    ),
]

WINDOWS_USER_PATH = re.compile(
    r"(?i)\b[A-Z]:\\Users\\([^\\/\s]+)\\"
)


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    return (
        not normalized
        or normalized in {"none", "null", "true", "false", "changeme", "example", "demo", "test"}
        or normalized.startswith("${")
        or normalized.startswith("<")
        or "your_" in normalized
        or "votre" in normalized
    )


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel == SCANNER_PATH:
            continue
        if path.name in LOCAL_STATE_FILES:
            continue
        if path.suffix.lower() in {
            ".xlsx", ".xlsm", ".xlsb", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip"
        }:
            continue
        if path.suffix and path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        yield path


def _load_terms(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    terms: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        if len(text) >= 3:
            terms.append(text.casefold())
    return terms


def _scan_text(path: Path, root: Path, terms: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    rel = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    for number, line in enumerate(text.splitlines(), start=1):
        user_path = WINDOWS_USER_PATH.search(line)
        if user_path:
            username = user_path.group(1).strip().casefold()
            if username not in PLACEHOLDER_USERNAMES:
                findings.append(Finding("windows_user_path", rel, number))

        for category, pattern in PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            if category == "credential_assignment" and _is_placeholder_secret(match.group(1)):
                continue
            findings.append(Finding(category, rel, number))

        folded = line.casefold()
        if any(term in folded for term in terms):
            findings.append(Finding("local_sensitive_term", rel, number))

    return findings


def _tracked_sensitive_files(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return findings

    for raw in result.stdout.splitlines():
        rel = raw.strip().replace("\\", "/")
        lower = rel.lower()
        if lower in {"app_config.json", "user_preferences.json", "user_preferences.json.tmp"}:
            findings.append(Finding("tracked_local_config", rel, 0))
        if lower.endswith((".xlsx", ".xlsm", ".xlsb")):
            findings.append(Finding("tracked_excel_workbook", rel, 0))
        if lower in {".privacy_terms.local", ".env", ".env.local"}:
            findings.append(Finding("tracked_local_secret_file", rel, 0))
    return findings


def scan(root: Path, terms_file: Path | None) -> list[Finding]:
    terms = _load_terms(terms_file)
    findings = _tracked_sensitive_files(root)
    for path in _iter_files(root):
        findings.extend(_scan_text(path, root, terms))
    return sorted(set(findings), key=lambda item: (item.path, item.line, item.category))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan the repository for common PII/secrets without printing matched values. "
            "Add confidential client/employee names to .privacy_terms.local (ignored by Git) "
            "to scan for organization-specific terms locally."
        )
    )
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--terms-file",
        default=".privacy_terms.local",
        help="Local denylist, one confidential term per line",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    terms_file = Path(args.terms_file)
    if not terms_file.is_absolute():
        terms_file = root / terms_file

    findings = scan(root, terms_file)
    if not findings:
        print("Privacy scan: PASS — no common PII/secret patterns detected in the current tree.")
        if terms_file.exists():
            print("Local confidential-term denylist was also checked.")
        else:
            print("Tip: create .privacy_terms.local for client/employee-specific local checks.")
        return 0

    print(f"Privacy scan: FAIL — {len(findings)} potential issue(s) detected.")
    print("Matched values are intentionally not printed.")
    for finding in findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        print(f"- {finding.category}: {location}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
