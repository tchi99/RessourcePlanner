from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.thunderbird_bridge import NATIVE_HOST_NAME, ThunderbirdSetupResult
from app.thunderbird_registry_install import (
    packaged_python_environment,
    publish_registry_fix,
    registry_fix_content,
)


class ThunderbirdRegistryInstallTests(unittest.TestCase):
    def _setup(self, root: Path) -> ThunderbirdSetupResult:
        manifest_path = root / f"{NATIVE_HOST_NAME}.json"
        manifest_path.write_text(json.dumps({"name": NATIVE_HOST_NAME}), encoding="utf-8")
        extension_path = root / "bridge.xpi"
        extension_path.write_bytes(b"xpi")
        return ThunderbirdSetupResult(
            extension_package=extension_path,
            integration_directory=root,
            native_host_registered=True,
        )

    def test_detects_store_python_from_virtualized_localappdata(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LOCALAPPDATA": (
                    r"C:\Users\example\AppData\Local\Packages\"
                    r"PythonSoftwareFoundation.Python.3.11_test\LocalCache\Local"
                )
            },
        ):
            self.assertTrue(packaged_python_environment())

    def test_registry_fix_contains_native_and_32_bit_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            setup = self._setup(root)
            content = registry_fix_content(setup)

            self.assertIn(
                rf"HKEY_CURRENT_USER\Software\Mozilla\NativeMessagingHosts\{NATIVE_HOST_NAME}",
                content,
            )
            self.assertIn(
                rf"HKEY_CURRENT_USER\Software\WOW6432Node\Mozilla\NativeMessagingHosts\{NATIVE_HOST_NAME}",
                content,
            )
            escaped_manifest = str(root / f"{NATIVE_HOST_NAME}.json").replace("\\", "\\\\")
            self.assertIn(escaped_manifest, content)

    def test_publish_registry_fix_writes_utf16_reg_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "bridge"
            root.mkdir()
            downloads = Path(temp_dir) / "downloads"
            setup = self._setup(root)

            path = publish_registry_fix(setup, destination_directory=downloads)

            self.assertTrue(path.is_file())
            decoded = path.read_text(encoding="utf-16")
            self.assertTrue(decoded.startswith("Windows Registry Editor Version 5.00"))
            self.assertIn(NATIVE_HOST_NAME, decoded)


if __name__ == "__main__":
    unittest.main()
