from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_config
from app.domain.plan_comparison import summarize_differences
from app.excel_repository import ExcelRepository
from app.planning_shadow import build_shadow_report


def _format_pairs(pairs: tuple[tuple[str, object], ...]) -> str:
    return ",".join(f"{name}:{value}" for name, value in pairs) or "none"


def main() -> int:
    config = load_config()
    repo = ExcelRepository(config.workbook, save_on_write=config.save_on_write)
    repo.connect()
    report = build_shadow_report(repo)

    comparison = report.comparison
    print("Planning shadow diagnostic")
    print(f"match={comparison.matches}")
    print(f"compared_keys={comparison.compared_keys}")
    print(f"difference_count={len(comparison.differences)}")
    print(f"unsupported_segment_count={len(report.unsupported_segment_ids)}")
    print(f"shadow_segment_count={report.shadow_result.segment_count}")
    print(f"shadow_locked_allocation_count={report.shadow_result.locked_allocation_count}")
    print(f"shadow_requested_hours={report.shadow_result.requested_hours:.2f}")
    print(f"shadow_allocated_hours={report.shadow_result.allocated_hours:.2f}")
    print(f"shadow_unallocated_hours={report.shadow_result.unallocated_hours:.2f}")

    if comparison.differences:
        summary = summarize_differences(comparison)
        estimated_legacy_total = (
            report.shadow_result.allocated_hours - summary.net_shadow_minus_legacy_hours
        )
        print(f"affected_segment_count={summary.affected_segment_count}")
        print(f"redistributed_segment_count={summary.redistributed_segment_count}")
        print(f"segment_total_delta_count={summary.segment_total_delta_count}")
        print(f"legacy_only_key_count={summary.legacy_only_key_count}")
        print(f"shadow_only_key_count={summary.shadow_only_key_count}")
        print(f"changed_key_count={summary.changed_key_count}")
        print(f"legacy_allocated_hours={estimated_legacy_total:.2f}")
        print(f"net_shadow_minus_legacy_hours={summary.net_shadow_minus_legacy_hours:.2f}")
        print(f"legacy_difference_hours={summary.legacy_difference_hours:.2f}")
        print(f"shadow_difference_hours={summary.shadow_difference_hours:.2f}")
        print(f"absolute_difference_hours={summary.absolute_difference_hours:.2f}")
        print(f"difference_count_by_type={_format_pairs(summary.difference_count_by_type)}")
        print(f"net_hours_by_type={_format_pairs(summary.net_hours_by_type)}")
        print("No resource names, project names, workbook paths, dates, or segment identifiers are printed.")
        return 2
    if report.unsupported_segment_ids:
        print("The comparable plan matches, but some active segments had no usable date window.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
