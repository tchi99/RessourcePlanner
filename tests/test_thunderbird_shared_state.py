from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import thunderbird_bridge
from app.thunderbird_shared_state import (
    BRIDGE_DIRECTORY_ENV,
    install_shared_bridge_directory,
    shared_bridge_directory,
)


class ThunderbirdSharedStateTests(unittest.TestCase):
    def test_shared_directory_uses_profile_not_localappdata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = Path(temp_dir) / "profile"
            packaged_local = Path(temp_dir) / "packages" / "python" / "LocalCache" / "Local"
            with patch.dict(
                os.environ,
                {
                    "USERPROFILE": str(profile),
                    "LOCALAPPDATA": str(packaged_local),
                    BRIDGE_DIRECTORY_ENV: "",
                },
                clear=False,
            ):
                self.assertEqual(
                    shared_bridge_directory(),
                    profile / ".ressourceplanner" / "ThunderbirdBridge",
                )

    def test_app_and_native_host_share_heartbeat_across_different_localappdata_views(self) -> None:
        original_directory = thunderbird_bridge._bridge_directory
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                profile = Path(temp_dir) / "profile"
                app_local = Path(temp_dir) / "packages" / "python" / "LocalCache" / "Local"
                thunderbird_local = Path(temp_dir) / "desktop-local"
                with patch.dict(
                    os.environ,
                    {
                        "USERPROFILE": str(profile),
                        "LOCALAPPDATA": str(app_local),
                        BRIDGE_DIRECTORY_ENV: "",
                    },
                    clear=False,
                ):
                    install_shared_bridge_directory()
                    thunderbird_bridge.handle_native_message({"action": "heartbeat"})

                with patch.dict(
                    os.environ,
                    {
                        "USERPROFILE": str(profile),
                        "LOCALAPPDATA": str(thunderbird_local),
                        BRIDGE_DIRECTORY_ENV: "",
                    },
                    clear=False,
                ):
                    status = thunderbird_bridge.thunderbird_batch_status("synthetic")
                    self.assertTrue(status.extension_seen_recently)
        finally:
            thunderbird_bridge._bridge_directory = original_directory


if __name__ == "__main__":
    unittest.main()
