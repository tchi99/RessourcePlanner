from __future__ import annotations

import argparse

from app.performance_diagnostics import (
    default_performance_log_path,
    format_performance_report,
    read_performance_samples,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Affiche les dernières métriques techniques de performance RessourcePlanner."
    )
    parser.add_argument("--limit", type=int, default=20, help="Nombre d'opérations à afficher.")
    parser.add_argument(
        "--path",
        action="store_true",
        help="Affiche aussi l'emplacement du journal local.",
    )
    args = parser.parse_args()

    if args.path:
        print(f"Journal: {default_performance_log_path()}")
    print(format_performance_report(read_performance_samples(limit=max(args.limit, 0))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
