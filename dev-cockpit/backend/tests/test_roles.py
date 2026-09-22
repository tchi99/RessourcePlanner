from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.roles import RoleStore, RolesConfig


class RoleStoreTests(unittest.TestCase):
    def test_defaults_are_returned_without_creating_a_file(self):
        with TemporaryDirectory() as temp_dir:
            store = RoleStore(temp_dir)
            config = store.load()

            self.assertEqual(
                [role.id for role in config.roles],
                ["product-owner", "developer", "architect"],
            )
            self.assertFalse(store.path.exists())

    def test_save_is_persistent_sorted_and_atomic(self):
        with TemporaryDirectory() as temp_dir:
            store = RoleStore(temp_dir)
            payload = RolesConfig.model_validate(
                {
                    "roles": [
                        {
                            "id": "developer",
                            "name": "DEV",
                            "avatar": "developer",
                            "chat_url": "https://chatgpt.com/c/example",
                            "enabled": True,
                            "order": 20,
                        },
                        {
                            "id": "product-owner",
                            "name": "Product Owner",
                            "avatar": "product-owner",
                            "chat_url": "",
                            "enabled": True,
                            "order": 10,
                        },
                    ]
                }
            )

            saved = store.save(payload)
            reloaded = store.load()

            self.assertEqual([role.id for role in saved.roles], ["product-owner", "developer"])
            self.assertEqual(saved, reloaded)
            raw = json.loads(Path(store.path).read_text(encoding="utf-8"))
            self.assertEqual(raw["roles"][1]["chat_url"], "https://chatgpt.com/c/example")
            self.assertEqual(list(Path(temp_dir).glob(".roles-*.tmp")), [])

    def test_rejects_duplicate_ids_and_invalid_url(self):
        with self.assertRaises(ValueError):
            RolesConfig.model_validate(
                {
                    "roles": [
                        {"id": "dev", "name": "A"},
                        {"id": "dev", "name": "B"},
                    ]
                }
            )
        with self.assertRaises(ValueError):
            RolesConfig.model_validate(
                {
                    "roles": [
                        {
                            "id": "dev",
                            "name": "Developer",
                            "chat_url": "ftp://invalid.example/chat",
                        }
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
