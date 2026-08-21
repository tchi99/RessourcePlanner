from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.thunderbird_shared_state import install_shared_bridge_directory

install_shared_bridge_directory()

from app.thunderbird_bridge import run_native_host


if __name__ == "__main__":
    raise SystemExit(run_native_host())
