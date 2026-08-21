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
    prepare_registry_visible_bundle,
    publish_registry_fix,
    registry_fix_content,
)


class ThunderbirdRegistryInstallTests(unittest.TestCase):
    def _setup(self, root: Path) -> ThunderbirdSetupResult:
        host_path = root / "thunderbird_native_host.bat"
        host_path.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
        manifest_path = root / f"{NATIVE_HOST_NAME}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "name": NATIVE_HOST_NAME,
                    "description": "test",
                    "path": str(host_path),
                    "type": "stdio",
                    "allowed_extensions": ["ressourceplanner-drafts@local"],
                }
            ),
            encoding="utf-8",
        )
        extension_path = root / "bridge.xpi"
        extension_path.write_bytes(b"xpi")
        return ThunderbirdSetupResult(
            extension_package=extension_path,
            integration_directory=root,
            native_host_registered=True,
        )

    def test_detects_store_python_from_virtualized_localappdata(self) -> None:
        virtualized_local = (
            "C:\\Users\\example\\AppData\\Local\\Packages\\"
            "PythonSoftwareFoundation.Python.3.11_test\\LocalCache\\Local"
        )
        with patch.dict(os.environ, {"LOCALAPPDATA": virtualized_local}):
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

    def test_stages_manifest_and_batch_outside_source_integration_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "virtualized"
            root.mkdir()
            bundle = Path(temp_dir) / "profile" / ".ressourceplanner" / "ThunderbirdBridge"
            setup = self._setup(root)

            staged_manifest = prepare_registry_visible_bundle(setup, bundle_directory=bundle)

            self.assertEqual(staged_manifest.parent, bundle)
            self.assertTrue(staged_manifest.is_file())
            payload = json.loads(staged_manifest.read_text(encoding="utf-8"))
            staged_host = Path(str(payload["path"]))
            self.assertEqual(staged_host.parent, bundle)
            self.assertTrue(staged_host.is_file())
            self.assertEqual(payload["name"], NATIVE_HOST_NAME)

    def test_publish_registry_fix_points_to_staged_profile_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "virtualized"
            root.mkdir()
            downloads = Path(temp_dir) / "downloads"
            bundle = Path(temp_dir) / "profile" / ".ressourceplanner" / "ThunderbirdBridge"
            setup = self._setup(root)

            path = publish_registry_fix(
                setup,
                destination_directory=downloads,
                bundle_directory=bundle,
            )

            self.assertTrue(path.is_file())
            decoded = path.read_text(encoding="utf-16")
            self.assertTrue(decoded.startswith("Windows Registry Editor Version 5.00"))
            self.assertIn(NATIVE_HOST_NAME, decoded)
            escaped_manifest = str(bundle / f"{NATIVE_HOST_NAME}.json").replace("\\", "\\\\")
            self.assertIn(escaped_manifest, decoded)
            self.assertNotIn(str(root).replace("\\", "\\\\"), decoded)


if __name__ == "__main__":
    unittest.main()
