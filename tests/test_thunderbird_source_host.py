from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.thunderbird_bridge import EXTENSION_ID, NATIVE_HOST_NAME, ThunderbirdSetupResult
from app.thunderbird_source_host import repair_source_host_launcher


class ThunderbirdSourceHostTests(unittest.TestCase):
    def test_repair_rewrites_batch_with_absolute_guards_and_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bridge = root / "bridge"
            bridge.mkdir()
            source = root / "source"
            tool_dir = source / "tools"
            tool_dir.mkdir(parents=True)
            tool = tool_dir / "thunderbird_native_host.py"
            tool.write_text("pass\n", encoding="utf-8")
            python = root / "python.exe"
            python.write_bytes(b"python")
            host = bridge / "thunderbird_native_host.bat"
            host.write_text("@echo off\r\n", encoding="utf-8")
            manifest = bridge / f"{NATIVE_HOST_NAME}.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": NATIVE_HOST_NAME,
                        "path": str(host),
                        "type": "stdio",
                        "allowed_extensions": [EXTENSION_ID],
                    }
                ),
                encoding="utf-8",
            )
            extension = bridge / "bridge.xpi"
            extension.write_bytes(b"xpi")
            setup = ThunderbirdSetupResult(extension, bridge, True)

            repaired = repair_source_host_launcher(
                setup,
                python_executable=python,
                source_root=source,
            )

            self.assertTrue(repaired)
            content = host.read_text(encoding="utf-8")
            self.assertIn('cd /d "%~dp0"', content)
            self.assertIn("RP_HOST_WORKDIR_NOT_FOUND", content)
            self.assertIn("RP_HOST_PYTHON_NOT_FOUND", content)
            self.assertIn("RP_HOST_SCRIPT_NOT_FOUND", content)
            self.assertIn(str(python.resolve()), content)
            self.assertIn(str(tool.resolve()), content)

    def test_packaged_executable_manifest_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = root / "RessourcePlanner-ThunderbirdHost.exe"
            host.write_bytes(b"host")
            manifest = root / f"{NATIVE_HOST_NAME}.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": NATIVE_HOST_NAME,
                        "path": str(host),
                        "type": "stdio",
                        "allowed_extensions": [EXTENSION_ID],
                    }
                ),
                encoding="utf-8",
            )
            extension = root / "bridge.xpi"
            extension.write_bytes(b"xpi")
            setup = ThunderbirdSetupResult(extension, root, True)

            self.assertFalse(repair_source_host_launcher(setup))


if __name__ == "__main__":
    unittest.main()
