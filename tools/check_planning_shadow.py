from __future__ import annotations

import sys

from app.config import load_config
from app.excel_repository import ExcelRepository
from app.planning_shadow import build_shadow_report


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
        absolute_delta = sum(
            abs(item.legacy_hours - item.shadow_hours)
            for item in comparison.differences
        )
        print(f"absolute_difference_hours={absolute_delta:.2f}")
        print("No resource names, project names, workbook paths, or segment identifiers are printed.")
        return 2
    if report.unsupported_segment_ids:
        print("The comparable plan matches, but some active segments had no usable date window.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
