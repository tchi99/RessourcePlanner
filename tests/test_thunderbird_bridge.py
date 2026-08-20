from __future__ import annotations

import io
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.thunderbird_bridge import (
    EXTENSION_ID,
    NATIVE_HOST_NAME,
    ThunderbirdDraftRequest,
    _EXTENSION_BACKGROUND,
    _EXTENSION_MANIFEST,
    _read_native_message,
    _write_native_message,
    handle_native_message,
    queue_thunderbird_drafts,
    run_native_host,
    thunderbird_batch_status,
    thunderbird_created_message_ids,
)


def synthetic_email(local: str) -> str:
    return local + chr(64) + "invalid.test"


class ThunderbirdBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": self.temp.name})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def request(self, message_id: str = "M1") -> ThunderbirdDraftRequest:
        return ThunderbirdDraftRequest(
            message_id=message_id,
            batch_id="B1",
            to_address=synthetic_email("recipient"),
            subject="Planning test",
            body="Corps test",
        )

    def test_extension_can_save_but_has_no_send_permission_or_call(self) -> None:
        permissions = set(_EXTENSION_MANIFEST["permissions"])
        self.assertIn("compose.save", permissions)
        self.assertIn("nativeMessaging", permissions)
        self.assertNotIn("compose.send", permissions)
        self.assertIn("saveMessage", _EXTENSION_BACKGROUND)
        self.assertNotIn("sendMessage(tab", _EXTENSION_BACKGROUND)
        self.assertNotIn("sendNow", _EXTENSION_BACKGROUND)
        self.assertEqual(
            _EXTENSION_MANIFEST["browser_specific_settings"]["gecko"]["id"],
            EXTENSION_ID,
        )

    def test_queue_poll_and_ack_marks_draft_created(self) -> None:
        self.assertEqual(queue_thunderbird_drafts([self.request()]), 1)
        polled = handle_native_message({"action": "poll"})
        self.assertTrue(polled["ok"])
        self.assertEqual([row["message_id"] for row in polled["messages"]], ["M1"])
        self.assertTrue(thunderbird_batch_status("B1").extension_seen_recently)

        handle_native_message(
            {"action": "ack", "results": [{"message_id": "M1", "ok": True}]}
        )
        status = thunderbird_batch_status("B1")
        self.assertEqual(status.total, 1)
        self.assertEqual(status.created, 1)
        self.assertEqual(status.pending, 0)
        self.assertEqual(thunderbird_created_message_ids("B1"), ("M1",))

    def test_failed_message_can_be_requeued_without_overwriting_created_one(self) -> None:
        queue_thunderbird_drafts([self.request("M1"), self.request("M2")])
        handle_native_message({"action": "poll"})
        handle_native_message(
            {
                "action": "ack",
                "results": [
                    {"message_id": "M1", "ok": True},
                    {"message_id": "M2", "ok": False, "error": "ExtensionError"},
                ],
            }
        )
        self.assertEqual(thunderbird_batch_status("B1").failed, 1)
        queued = queue_thunderbird_drafts([self.request("M1"), self.request("M2")])
        self.assertEqual(queued, 1)
        status = thunderbird_batch_status("B1")
        self.assertEqual(status.created, 1)
        self.assertEqual(status.pending, 1)

    def test_native_message_protocol_round_trip(self) -> None:
        payload = {"action": "heartbeat"}
        buffer = io.BytesIO()
        _write_native_message(buffer, payload)
        buffer.seek(0)
        self.assertEqual(_read_native_message(buffer), payload)

        encoded = json.dumps(payload).encode("utf-8")
        source = io.BytesIO(struct.pack("<I", len(encoded)) + encoded)
        target = io.BytesIO()
        self.assertEqual(run_native_host(source, target), 0)
        target.seek(0)
        response = _read_native_message(target)
        self.assertTrue(response["ok"])

    def test_native_host_name_is_valid_mozilla_style(self) -> None:
        self.assertEqual(NATIVE_HOST_NAME, "com.ressourceplanner.bridge")
        self.assertNotIn("-", NATIVE_HOST_NAME)


if __name__ == "__main__":
    unittest.main()
