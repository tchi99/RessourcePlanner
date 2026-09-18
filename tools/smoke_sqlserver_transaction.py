from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from sqlalchemy import insert, select
from sqlalchemy.exc import DBAPIError, NoSuchModuleError


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infrastructure.sql import create_sql_engine
from app.infrastructure.sql.models import Project
from tools.check_server_runtime import (
    ConnectivityReadinessError,
    DriverReadinessError,
    MigrationReadinessError,
    check_database_preflight,
)


DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"


def main() -> int:
    database_url = str(os.getenv(DATABASE_URL_ENV) or "").strip()
    if not database_url:
        print(json.dumps({"status": "configuration_error", "message": f"{DATABASE_URL_ENV} est requis."}, ensure_ascii=False))
        return 2

    try:
        preflight = check_database_preflight(database_url)
    except DriverReadinessError as exc:
        print(json.dumps({"status": "driver_error", "message": str(exc)}, ensure_ascii=False))
        return 3
    except ConnectivityReadinessError as exc:
        print(json.dumps({"status": "connectivity_error", "message": str(exc)}, ensure_ascii=False))
        return 4
    except MigrationReadinessError as exc:
        print(json.dumps({"status": "migration_error", "message": str(exc)}, ensure_ascii=False))
        return 5

    if preflight["database"] != "mssql":
        print(json.dumps({"status": "configuration_error", "message": "Ce smoke est réservé à SQL Server/MSSQL."}, ensure_ascii=False))
        return 2

    marker = uuid4().hex
    row_id = str(uuid4())
    project_number = f"ROLLBACK-{marker[:16]}"

    try:
        engine = create_sql_engine(database_url)
    except (ModuleNotFoundError, ImportError, NoSuchModuleError):
        print(json.dumps({"status": "driver_error", "message": "Le driver MSSQL/ODBC n'est pas disponible."}, ensure_ascii=False))
        return 3

    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    insert(Project).values(
                        id=row_id,
                        number=project_number,
                        name="SQL Server rollback smoke",
                        status="smoke",
                    )
                )
                visible = connection.scalar(
                    select(Project.id).where(Project.id == row_id)
                )
                if visible != row_id:
                    raise RuntimeError("La ligne de smoke n'est pas visible dans sa transaction.")
            finally:
                transaction.rollback()

        with engine.connect() as verification:
            persisted = verification.scalar(
                select(Project.id).where(Project.id == row_id)
            )
        if persisted is not None:
            print(json.dumps({"status": "rollback_error", "message": "La ligne de smoke existe après rollback."}, ensure_ascii=False))
            return 7
    except DBAPIError:
        print(json.dumps({"status": "transaction_error", "message": "Le smoke transactionnel SQL Server a échoué."}, ensure_ascii=False))
        return 6
    finally:
        engine.dispose()

    print(json.dumps({
        "status": "ok",
        "database": "mssql",
        "alembic_revision": preflight["alembic_revision"],
        "smoke": "transaction_rollback",
        "rollback_verified": True,
        "business_rows_persisted": 0,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
