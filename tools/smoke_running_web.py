from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _get(base_url: str, path: str, *, timeout: float) -> tuple[int, str, str]:
    request = Request(
        base_url.rstrip("/") + path,
        headers={"Accept": "application/json,text/html;q=0.9"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(1_000_000).decode("utf-8", errors="replace")
            return int(response.status), str(response.headers.get("Content-Type") or ""), body
    except HTTPError as exc:
        body = exc.read(100_000).decode("utf-8", errors="replace")
        return int(exc.code), str(exc.headers.get("Content-Type") or ""), body


def _json(body: str) -> dict[str, Any]:
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("JSON object expected")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke du runtime Web déjà démarré.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Origine du runtime, sans chemin.",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    try:
        health_status, _, health_body = _get(args.base_url, "/health", timeout=args.timeout)
        ready_status, _, ready_body = _get(args.base_url, "/ready", timeout=args.timeout)
        root_status, root_type, root_body = _get(args.base_url, "/", timeout=args.timeout)
    except (URLError, TimeoutError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "runtime_unreachable",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 1

    try:
        health = _json(health_body)
        ready = _json(ready_body)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({"status": "failed", "reason": "probe_invalid_json"}, sort_keys=True))
        return 1

    failures: list[str] = []
    if health_status != 200 or health.get("status") != "ok":
        failures.append("health")
    if ready_status != 200 or ready.get("status") != "ready":
        failures.append("readiness")
    if root_status != 200 or "text/html" not in root_type.casefold() or "<html" not in root_body.casefold():
        failures.append("frontend")

    database = ready.get("database") if isinstance(ready.get("database"), dict) else {}
    payload = {
        "status": "ok" if not failures else "failed",
        "health": health.get("status"),
        "readiness": ready.get("status"),
        "database": database.get("dialect"),
        "alembic_revision": database.get("alembic_revision"),
        "frontend": "ok" if "frontend" not in failures else "failed",
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
