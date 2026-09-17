from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy.exc import SQLAlchemyError

from app.application import ApplicationError, ProjectSyncResult, ProjectSyncService
from app.infrastructure.erp_export import ErpExcelProjectSource
from app.infrastructure.sql import create_session_factory, create_sql_engine
from app.infrastructure.sql.project_sync_repository import SqlProjectSyncRepository


DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///./resourceplanner_server.db"


def resolve_database_url(explicit: str | None = None) -> str:
    return (explicit or os.getenv(DATABASE_URL_ENV) or DEFAULT_DATABASE_URL).strip()


def synchronize_file(
    xlsx_path: str | Path,
    *,
    database_url: str,
    apply: bool,
) -> ProjectSyncResult:
    source = ErpExcelProjectSource(xlsx_path)
    engine = create_sql_engine(database_url)
    factory = create_session_factory(engine)
    session = factory()
    transaction = session.begin()
    try:
        result = ProjectSyncService(
            source,
            SqlProjectSyncRepository(session),
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


def _result_text(result: ProjectSyncResult, *, preview: bool) -> str:
    prefix = "Prévisualisation" if preview else "Import terminé"
    return (
        f"{prefix}\n\n"
        f"Projets lus : {result.received}\n"
        f"À créer : {result.created}\n"
        f"À mettre à jour : {result.updated}\n"
        f"Sans changement : {result.unchanged}"
    )


def run_gui(*, database_url: str) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        xlsx_path = filedialog.askopenfilename(
            title="Sélectionner l'export des projets ERP",
            filetypes=[("Fichier Excel", "*.xlsx"), ("Tous les fichiers", "*.*")],
        )
        if not xlsx_path:
            return 0

        preview = synchronize_file(xlsx_path, database_url=database_url, apply=False)
        confirm = messagebox.askyesno(
            "Import des projets ERP",
            _result_text(preview, preview=True)
            + "\n\nAucune modification n'a encore été enregistrée.\n"
            + "Voulez-vous appliquer cet import?",
        )
        if not confirm:
            return 0

        applied = synchronize_file(xlsx_path, database_url=database_url, apply=True)
        messagebox.showinfo("Import des projets ERP", _result_text(applied, preview=False))
        return 0
    except ApplicationError as exc:
        messagebox.showerror("Import des projets ERP", str(exc))
        return 2
    except SQLAlchemyError as exc:
        messagebox.showerror(
            "Import des projets ERP",
            "Impossible d'accéder à la base de données. "
            "Vérifie que la base SQLite existe et que ses migrations sont à jour.\n\n"
            f"Détail : {exc}",
        )
        return 3
    except Exception as exc:
        messagebox.showerror("Import des projets ERP", f"Erreur inattendue : {exc}")
        return 4
    finally:
        root.destroy()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prévisualiser ou importer un export XLSX des projets ERP dans RessourcePlanner."
    )
    parser.add_argument("xlsx", nargs="?", help="Chemin du fichier XLSX exporté de l'ERP.")
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
    if args.gui or not args.xlsx:
        return run_gui(database_url=database_url)

    try:
        result = synchronize_file(args.xlsx, database_url=database_url, apply=args.apply)
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
