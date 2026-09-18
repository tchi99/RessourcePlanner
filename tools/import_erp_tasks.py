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
from app.application.task_catalog import TaskCatalogSyncResult, TaskCatalogSyncService
from app.infrastructure.erp_export import ErpTaskCatalogFileSource
from app.infrastructure.sql.session import create_session_factory, create_sql_engine
from app.infrastructure.sql.task_catalog_repository import SqlTaskCatalogRepository


DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///./resourceplanner_server.db"


def resolve_database_url(explicit: str | None = None) -> str:
    return (explicit or os.getenv(DATABASE_URL_ENV) or DEFAULT_DATABASE_URL).strip()


def synchronize_file(
    export_path: str | Path,
    *,
    database_url: str,
    apply: bool,
) -> TaskCatalogSyncResult:
    source = ErpTaskCatalogFileSource(export_path)
    engine = create_sql_engine(database_url)
    factory = create_session_factory(engine)
    session = factory()
    transaction = session.begin()
    try:
        result = TaskCatalogSyncService(
            source,
            SqlTaskCatalogRepository(session),
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


def _result_text(result: TaskCatalogSyncResult, *, preview: bool) -> str:
    prefix = "Prévisualisation" if preview else "Import terminé"
    return (
        f"{prefix}\n\n"
        f"Tâches lues : {result.received}\n"
        f"À créer : {result.created}\n"
        f"À mettre à jour : {result.updated}\n"
        f"À désactiver : {result.deactivated}\n"
        f"Sans changement : {result.unchanged}"
    )


def run_gui(*, database_url: str) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        export_path = filedialog.askopenfilename(
            title="Sélectionner l'export des tâches ERP",
            filetypes=[
                ("Exports ERP", "*.xlsx *.xlsm *.csv"),
                ("Fichiers Excel", "*.xlsx *.xlsm"),
                ("Fichiers CSV", "*.csv"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if not export_path:
            return 0

        preview = synchronize_file(export_path, database_url=database_url, apply=False)
        confirm = messagebox.askyesno(
            "Import du catalogue de tâches ERP",
            _result_text(preview, preview=True)
            + "\n\nAucune modification n'a encore été enregistrée.\n"
            + "Voulez-vous appliquer cet import?",
        )
        if not confirm:
            return 0

        applied = synchronize_file(export_path, database_url=database_url, apply=True)
        messagebox.showinfo(
            "Import du catalogue de tâches ERP",
            _result_text(applied, preview=False),
        )
        return 0
    except ApplicationError as exc:
        messagebox.showerror("Import du catalogue de tâches ERP", str(exc))
        return 2
    except SQLAlchemyError as exc:
        messagebox.showerror(
            "Import du catalogue de tâches ERP",
            "Impossible d'accéder à la base de données. "
            "Vérifie que les migrations sont à jour.\n\n"
            f"Détail : {exc}",
        )
        return 3
    except Exception as exc:
        messagebox.showerror(
            "Import du catalogue de tâches ERP",
            f"Erreur inattendue : {exc}",
        )
        return 4
    finally:
        root.destroy()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prévisualiser ou importer un export XLSX/CSV des tâches ERP."
    )
    parser.add_argument(
        "export",
        nargs="?",
        help="Chemin du fichier XLSX/XLSM/CSV exporté de l'ERP.",
    )
    parser.add_argument(
        "--database-url",
        help=f"URL SQLAlchemy. Défaut: ${DATABASE_URL_ENV}, puis {DEFAULT_DATABASE_URL}.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Enregistre les changements. Sans cette option, l'import est simulé puis annulé.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Ouvre le sélecteur de fichier et demande confirmation avant l'import.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = resolve_database_url(args.database_url)
    if args.gui or not args.export:
        return run_gui(database_url=database_url)

    try:
        result = synchronize_file(args.export, database_url=database_url, apply=args.apply)
    except ApplicationError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(f"Erreur base de données: {exc}", file=sys.stderr)
        return 3

    print(_result_text(result, preview=not args.apply))
    if not args.apply:
        print("\nAucune modification enregistrée. Relance avec --apply pour importer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
