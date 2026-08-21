from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.thunderbird_bridge import EXTENSION_ID, NATIVE_HOST_NAME, ThunderbirdSetupResult
from app.thunderbird_native_diagnostics import (
    _probe_command,
    inspect_native_manifest,
    probe_native_host_launch,
    repair_and_diagnose_native_host,
)


class _Completed:
    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = b""


class ThunderbirdNativeDiagnosticsTests(unittest.TestCase):
    def _setup(self, root: Path, host_path: Path) -> ThunderbirdSetupResult:
        manifest = {
            "name": NATIVE_HOST_NAME,
            "description": "test",
            "path": str(host_path),
            "type": "stdio",
            "allowed_extensions": [EXTENSION_ID],
        }
        (root / f"{NATIVE_HOST_NAME}.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        extension = root / "bridge.xpi"
        extension.write_bytes(b"xpi")
        return ThunderbirdSetupResult(
            extension_package=extension,
            integration_directory=root,
            native_host_registered=True,
        )

    def test_manifest_validation_accepts_expected_host_and_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = root / "host.exe"
            host.write_bytes(b"host")
            setup = self._setup(root, host)

            ok, resolved_host, detail = inspect_native_manifest(setup)

            self.assertTrue(ok)
            self.assertEqual(resolved_host, host)
            self.assertEqual(detail, "")

    def test_manifest_validation_rejects_wrong_extension_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = root / "host.exe"
            host.write_bytes(b"host")
            setup = self._setup(root, host)
            manifest_path = root / f"{NATIVE_HOST_NAME}.json"
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["allowed_extensions"] = ["other" + chr(64) + "invalid.test"]
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")

            ok, _host, detail = inspect_native_manifest(setup)

            self.assertFalse(ok)
            self.assertIn("n'est pas autorisée", detail)

    def test_probe_launch_uses_eof_and_does_not_send_fake_native_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            host = Path(temp_dir) / "host.exe"
            host.write_bytes(b"host")
            calls: list[tuple[list[str], dict[str, object]]] = []

            def fake_runner(command, **kwargs):
                calls.append((list(command), dict(kwargs)))
                return _Completed(0)

            ok, detail = probe_native_host_launch(host, runner=fake_runner)

            self.assertTrue(ok)
            self.assertEqual(detail, "")
            self.assertEqual(calls[0][0], [str(host)])
            self.assertEqual(calls[0][1]["input"], b"")

    def test_windows_batch_probe_keeps_call_and_path_as_separate_arguments(self) -> None:
        host = Path(r"C:\Users\Test User\RessourcePlanner\thunderbird_native_host.bat")
        comspec = r"C:\Windows\System32\cmd.exe"
        with patch("app.thunderbird_native_diagnostics.os.name", "nt"), patch.dict(
            os.environ, {"COMSPEC": comspec}
        ):
            command = _probe_command(host)

        self.assertEqual(command, [comspec, "/d", "/c", "call", str(host)])
        self.assertNotIn('call "', " ".join(command[:4]))

    def test_diagnostic_reports_host_launch_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = root / "host.exe"
            host.write_bytes(b"host")
            setup = self._setup(root, host)

            def failing_runner(_command, **_kwargs):
                return _Completed(7, b"synthetic failure")

            diagnostic = repair_and_diagnose_native_host(setup, runner=failing_runner)

            self.assertFalse(diagnostic.ok)
            self.assertTrue(diagnostic.manifest_ok)
            self.assertTrue(diagnostic.host_exists)
            self.assertFalse(diagnostic.host_launch_ok)
            self.assertIn("code 7", diagnostic.detail)
            self.assertIn("synthetic failure", diagnostic.detail)


if __name__ == "__main__":
    unittest.main()
