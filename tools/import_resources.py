from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy.exc import SQLAlchemyError

from app.application.errors import ApplicationError
from app.application.resource_bootstrap import ResourceBootstrapResult, ResourceBootstrapService
from app.infrastructure.erp_export import ResourceBootstrapFileSource
from app.infrastructure.sql.resource_admin_repository import SqlResourceAdminRepository
from app.infrastructure.sql.session import create_session_factory, create_sql_engine


DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///./resourceplanner_server.db"


def resolve_database_url(explicit: str | None = None) -> str:
    return (explicit or os.getenv(DATABASE_URL_ENV) or DEFAULT_DATABASE_URL).strip()


def synchronize_file(
    export_path: str | Path,
    *,
    database_url: str,
    apply: bool,
    sheet_name: str = "Ressources",
) -> ResourceBootstrapResult:
    source = ResourceBootstrapFileSource(export_path, sheet_name=sheet_name)
    engine = create_sql_engine(database_url)
    factory = create_session_factory(engine)
    session = factory()
    transaction = session.begin()
    try:
        result = ResourceBootstrapService(
            source,
            SqlResourceAdminRepository(session),
        ).synchronize()
        if apply:
            transaction.commit()
        else:
            transaction.rollback()
        return result
    except Exception:
        if transaction.is_active:
            transaction.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def _result_text(result: ResourceBootstrapResult, *, preview: bool) -> str:
    prefix = "Prévisualisation" if preview else "Import terminé"
    return (
        f"{prefix}\n\n"
        f"Ressources lues : {result.received}\n"
        f"À créer : {result.created}\n"
        f"À mettre à jour : {result.updated}\n"
        f"Sans changement : {result.unchanged}\n"
        f"Lignes invalides : {result.invalid}\n"
        f"Horaires standards à créer : {result.schedules_created}\n"
        f"Horaires déjà identiques : {result.schedules_unchanged}\n"
        f"Horaires existants conservés : {result.schedules_preserved}\n"
        f"Sans horaire fourni : {result.without_schedule}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prévisualiser ou importer un bootstrap XLSX/CSV de ressources."
    )
    parser.add_argument("export", help="Chemin du fichier XLSX/XLSM/CSV.")
    parser.add_argument(
        "--database-url",
        help="URL SQLAlchemy. Défaut: RESOURCEPLANNER_DATABASE_URL, puis sqlite:///./resourceplanner_server.db.",
    )
    parser.add_argument("--sheet-name", default="Ressources")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Enregistre les changements. Sans cette option, l'import est simulé puis annulé.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = synchronize_file(
            args.export,
            database_url=resolve_database_url(args.database_url),
            apply=args.apply,
            sheet_name=args.sheet_name,
        )
    except ApplicationError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        print("Import annulé; aucune modification enregistrée.", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(f"Erreur base de données: {exc}", file=sys.stderr)
        print("Import annulé; aucune modification enregistrée.", file=sys.stderr)
        return 3
    print(_result_text(result, preview=not args.apply))
    if not args.apply:
        print("\nAucune modification enregistrée. Relance avec --apply pour importer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
