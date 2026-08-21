from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.thunderbird_extension_diagnostics import (
    DIAGNOSTIC_EXTENSION_VERSION,
    enhance_thunderbird_extension,
)


class ThunderbirdExtensionDiagnosticsTests(unittest.TestCase):
    def test_enhancement_bumps_version_and_adds_visible_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            xpi = Path(temp_dir) / "bridge.xpi"
            manifest = {
                "manifest_version": 2,
                "name": "Bridge",
                "version": "1.0.0",
                "permissions": ["compose", "nativeMessaging"],
                "background": {"scripts": ["background.js"]},
            }
            with zipfile.ZipFile(xpi, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest))
                archive.writestr("background.js", 'const HOST = "com.ressourceplanner.bridge";\n')

            enhance_thunderbird_extension(xpi)

            with zipfile.ZipFile(xpi, "r") as archive:
                updated = json.loads(archive.read("manifest.json").decode("utf-8"))
                background = archive.read("background.js").decode("utf-8")
                popup = archive.read("diagnostic.js").decode("utf-8")
                names = set(archive.namelist())

            self.assertEqual(updated["version"], DIAGNOSTIC_EXTENSION_VERSION)
            self.assertIn("storage", updated["permissions"])
            self.assertEqual(
                updated["browser_action"]["default_popup"],
                "diagnostic.html",
            )
            self.assertIn("diagnostic.html", names)
            self.assertIn("diagnostic.js", names)
            self.assertIn("sendNativeMessage", popup)
            self.assertIn("heartbeatNativeBridge", background)
            self.assertNotIn("compose.send", updated["permissions"])

    def test_enhancement_is_idempotent_for_background_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            xpi = Path(temp_dir) / "bridge.xpi"
            manifest = {
                "manifest_version": 2,
                "name": "Bridge",
                "version": "1.0.0",
                "permissions": ["nativeMessaging"],
                "background": {"scripts": ["background.js"]},
            }
            with zipfile.ZipFile(xpi, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest))
                archive.writestr("background.js", 'const HOST = "com.ressourceplanner.bridge";\n')

            enhance_thunderbird_extension(xpi)
            enhance_thunderbird_extension(xpi)

            with zipfile.ZipFile(xpi, "r") as archive:
                background = archive.read("background.js").decode("utf-8")
            self.assertEqual(
                background.count("RessourcePlanner extension diagnostics v1.1.0"),
                1,
            )


if __name__ == "__main__":
    unittest.main()
