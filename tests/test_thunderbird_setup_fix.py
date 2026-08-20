from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.communication_thunderbird_setup_fix import (
    EXTENSION_FILENAME,
    preferred_visible_install_directory,
    publish_thunderbird_extension,
    reveal_thunderbird_extension,
)


class ThunderbirdSetupFixTests(unittest.TestCase):
    def test_downloads_is_preferred_over_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            (home / "Documents").mkdir()
            (home / "Downloads").mkdir()
            self.assertEqual(
                preferred_visible_install_directory(home),
                home / "Downloads",
            )

    def test_documents_is_used_when_downloads_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            (home / "Documents").mkdir()
            self.assertEqual(
                preferred_visible_install_directory(home),
                home / "Documents",
            )

    def test_publish_copies_xpi_to_visible_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "hidden"
            source_dir.mkdir()
            home = root / "home"
            downloads = home / "Downloads"
            downloads.mkdir(parents=True)
            source = source_dir / EXTENSION_FILENAME
            source.write_bytes(b"demo-xpi")

            published = publish_thunderbird_extension(source, home=home)

            self.assertEqual(published, downloads / EXTENSION_FILENAME)
            self.assertEqual(published.read_bytes(), b"demo-xpi")

    def test_reveal_selects_exact_xpi_in_explorer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            xpi = Path(temp_dir) / EXTENSION_FILENAME
            xpi.write_bytes(b"demo-xpi")
            calls: list[list[str]] = []

            def fake_launcher(command):
                calls.append(list(command))
                return object()

            revealed = reveal_thunderbird_extension(
                xpi,
                platform_name="nt",
                launcher=fake_launcher,
            )

            self.assertEqual(revealed, xpi)
            self.assertEqual(
                calls,
                [["explorer.exe", "/select,", str(xpi)]],
            )


if __name__ == "__main__":
    unittest.main()
