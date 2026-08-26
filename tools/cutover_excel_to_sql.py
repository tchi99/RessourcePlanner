from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config

from app.config import load_config
from app.infrastructure.migration import import_cutover_dataset
from app.infrastructure.migration.openpyxl_reader import (
    CutoverSourceError,
    OpenpyxlCutoverReader,
)
from app.infrastructure.migration.preflight import build_cutover_preflight
from app.infrastructure.sql import (
    create_session_factory,
    create_sql_engine,
    transactional_session,
)


DEFAULT_REPORT = ROOT / "cutover_report.json"
DATABASE_ENV = "RESOURCEPLANNER_DATABASE_URL"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    value = result.stdout.strip()
    return value or None


def _workbook_path(argument: str | None) -> Path:
    if argument:
        path = Path(argument).expanduser().resolve()
    else:
        configured = load_config().workbook
        if configured is None:
            raise CutoverSourceError(
                "Aucun --workbook fourni et aucun classeur n'est configuré dans app_config.json."
            )
        path = configured.resolve()
    if not path.exists():
        raise CutoverSourceError(f"Classeur introuvable: {path}")
    return path


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    # ConfigParser interprets percent signs; encoded ODBC URLs often contain them.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _summary(payload: dict[str, Any]) -> None:
    preflight = payload.get("preflight") or {}
    mode = payload.get("mode") or "dry-run"
    print(f"Cutover RessourcePlanner — {mode}")
    print(f"Classeur: {payload.get('workbook')}")
    if preflight:
        print(
            "Préflight: "
            f"{'OK' if preflight.get('ok') else 'BLOQUÉ'} · "
            f"erreurs={preflight.get('blocking_error_count', 0)}"
        )
        counts = preflight.get("counts") or {}
        print(
            "Données: "
            f"demandes={counts.get('demands', 0)} · "
            f"segments={counts.get('requirements', 0)} · "
            f"quarts={counts.get('shifts', 0)} · "
            f"verrouillés={counts.get('locked_shifts', 0)}"
        )
    if payload.get("import"):
        print(f"Import SQL: {'OK' if payload['import'].get('ok') else 'ÉCHEC'}")
    if payload.get("error"):
        print(f"Erreur: {payload['error']}")
    print(f"Rapport: {payload.get('report_path')}")


def run_cutover(
    *,
    workbook: str | None,
    report_path: str | Path,
    apply: bool,
) -> int:
    report_file = Path(report_path).expanduser().resolve()
    payload: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "report_path": str(report_file),
        "source_commit": _git_commit(),
    }

    try:
        source_path = _workbook_path(workbook)
        payload["workbook"] = str(source_path)
        payload["workbook_size_bytes"] = source_path.stat().st_size
        before_hash = _sha256(source_path)
        payload["workbook_sha256"] = before_hash

        with OpenpyxlCutoverReader(source_path) as reader:
            preflight = build_cutover_preflight(reader)

        after_read_hash = _sha256(source_path)
        if after_read_hash != before_hash:
            raise CutoverSourceError(
                "Le classeur a changé pendant le préflight. Gèle les modifications et recommence."
            )

        payload["preflight"] = preflight.as_dict()
        if not preflight.ok:
            payload["ready_for_apply"] = False
            _write_report(report_file, payload)
            _summary(payload)
            return 2

        payload["ready_for_apply"] = True
        if not apply:
            _write_report(report_file, payload)
            _summary(payload)
            return 0

        database_url = os.environ.get(DATABASE_ENV, "").strip()
        if not database_url:
            raise RuntimeError(
                f"La variable {DATABASE_ENV} est requise avec --apply."
            )

        # Migration is explicit here, as part of the cutover command. Normal
        # application startup never runs opportunistic schema migrations.
        command.upgrade(_alembic_config(database_url), "head")

        engine = create_sql_engine(database_url)
        try:
            factory = create_session_factory(engine)
            with transactional_session(factory) as session:
                imported = import_cutover_dataset(
                    session,
                    preflight.report,
                    demand_work_package_links=preflight.demand_work_package_links,
                )
                # Fail closed if someone modified the source after extraction but before
                # the SQL transaction would commit.
                final_hash = _sha256(source_path)
                if final_hash != before_hash:
                    raise CutoverSourceError(
                        "Le classeur a changé pendant l'import SQL. Transaction annulée."
                    )
                payload["import"] = imported.as_dict()
                payload["database_dialect"] = engine.dialect.name
        finally:
            engine.dispose()

        payload["applied"] = True
        _write_report(report_file, payload)
        _summary(payload)
        return 0
    except Exception as exc:
        payload["applied"] = False
        payload["error_type"] = type(exc).__name__
        payload["error"] = str(exc)
        _write_report(report_file, payload)
        _summary(payload)
        return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Préflight et import one-shot du classeur V1 vers SQL."
    )
    parser.add_argument(
        "--workbook",
        help="Chemin du classeur V1 gelé. Par défaut, utilise app_config.json.",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT),
        help=f"Rapport JSON (défaut: {DEFAULT_REPORT}).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Applique les migrations Alembic puis importe dans la base indiquée par "
            f"{DATABASE_ENV}. Sans ce flag, aucune écriture SQL n'est effectuée."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cutover(
        workbook=args.workbook,
        report_path=args.report,
        apply=bool(args.apply),
    )


if __name__ == "__main__":
    sys.exit(main())
