from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from sqlalchemy import inspect, select
from sqlalchemy.exc import DBAPIError, NoSuchModuleError


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infrastructure.sql import create_sql_engine
from app.infrastructure.sql.models import Project, Resource, ResourceRequirement, Shift, WorkforceRequest
from tools.check_server_runtime import (
    ConnectivityReadinessError,
    DriverReadinessError,
    MigrationReadinessError,
    check_database_preflight,
)


DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"
REQUIRED_TABLES = {
    "projects",
    "resources",
    "workforce_requests",
    "resource_requirements",
    "shifts",
    "alembic_version",
}


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

    try:
        engine = create_sql_engine(database_url)
    except (ModuleNotFoundError, ImportError, NoSuchModuleError):
        print(json.dumps({"status": "driver_error", "message": "Le driver MSSQL/ODBC n'est pas disponible."}, ensure_ascii=False))
        return 3

    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            missing = sorted(REQUIRED_TABLES - tables)
            if missing:
                print(json.dumps({"status": "readiness_error", "message": "Tables requises absentes.", "missing_tables": missing}, ensure_ascii=False))
                return 6

            probes = (
                ("projects", select(Project.id).limit(1)),
                ("resources", select(Resource.id).limit(1)),
                ("demands", select(WorkforceRequest.id).limit(1)),
                ("segments", select(ResourceRequirement.id).limit(1)),
                ("shifts", select(Shift.id).limit(1)),
            )
            for _name, statement in probes:
                connection.execute(statement).first()
    except DBAPIError:
        print(json.dumps({"status": "readiness_error", "message": "Une lecture SQL Server non destructive a échoué."}, ensure_ascii=False))
        return 6
    finally:
        engine.dispose()

    print(json.dumps({
        "status": "ok",
        "database": "mssql",
        "alembic_revision": preflight["alembic_revision"],
        "smoke": "read_only",
        "tables_checked": len(REQUIRED_TABLES),
        "business_rows_modified": 0,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
