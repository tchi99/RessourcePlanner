from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from app.outlook_drafts import (
    OutlookDraftRequest,
    OutlookDraftTransportError,
    _powershell_script,
    create_outlook_drafts,
)


class OutlookDraftTransportTests(unittest.TestCase):
    def request(self, message_id: str = "M1") -> OutlookDraftRequest:
        return OutlookDraftRequest(
            message_id=message_id,
            batch_id="B1",
            to_address="recipient@invalid.test",
            subject="Planning démo",
            body="Corps de test",
        )

    def test_powershell_transport_contains_save_but_no_send_call(self) -> None:
        script = _powershell_script()
        self.assertIn("$mail.Save()", script)
        self.assertNotIn("$mail.Send()", script)
        self.assertNotIn(".Send(", script)

    def test_runner_receives_json_payload_and_parses_created_and_existing(self) -> None:
        captured: dict[str, object] = {}

        def fake_runner(command, **kwargs):
            input_path = Path(command[-1])
            captured["payload"] = json.loads(input_path.read_text(encoding="utf-8"))
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"created":["M1"],"existing":["M2"],"failed":[]}',
                stderr="",
            )

        result = create_outlook_drafts(
            [self.request("M1"), self.request("M2")],
            runner=fake_runner,
            platform_name="nt",
        )
        self.assertEqual(result.created_message_ids, ("M1",))
        self.assertEqual(result.existing_message_ids, ("M2",))
        self.assertEqual(result.completed_message_ids, ("M1", "M2"))
        payload = captured["payload"]
        self.assertEqual([row["message_id"] for row in payload["messages"]], ["M1", "M2"])

    def test_partial_failure_is_reported_without_losing_created_ids(self) -> None:
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"created":["M1"],"existing":[],"failed":{"message_id":"M2","error":"ComError"}}',
                stderr="",
            )

        result = create_outlook_drafts(
            [self.request("M1"), self.request("M2")],
            runner=fake_runner,
            platform_name="nt",
        )
        self.assertEqual(result.created_message_ids, ("M1",))
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].message_id, "M2")

    def test_com_unavailable_returns_clear_transport_error(self) -> None:
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                20,
                stdout="",
                stderr="OUTLOOK_COM_UNAVAILABLE",
            )

        with self.assertRaisesRegex(OutlookDraftTransportError, "Outlook"):
            create_outlook_drafts(
                [self.request()],
                runner=fake_runner,
                platform_name="nt",
            )

    def test_blank_recipient_is_rejected_before_transport(self) -> None:
        request = OutlookDraftRequest(
            message_id="M1",
            batch_id="B1",
            to_address="",
            subject="Sujet",
            body="Corps",
        )
        with self.assertRaises(ValueError):
            create_outlook_drafts(
                [request],
                runner=lambda *args, **kwargs: None,
                platform_name="nt",
            )


if __name__ == "__main__":
    unittest.main()
