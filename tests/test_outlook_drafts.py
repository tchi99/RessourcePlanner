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


def synthetic_email(local: str) -> str:
    return local + chr(64) + "invalid.test"


class OutlookDraftTransportTests(unittest.TestCase):
    def request(self, message_id: str = "M1") -> OutlookDraftRequest:
        return OutlookDraftRequest(
            message_id=message_id,
            batch_id="B1",
            to_address=synthetic_email("recipient"),
            subject="Planning démo",
            body="Corps de test",
        )

    def test_powershell_transport_contains_save_but_no_send_call(self) -> None:
        script = _powershell_script()
        self.assertIn("$mail.Save()", script)
        self.assertNotIn("$mail.Send()", script)
        self.assertNotIn(".Send(", script)

    def test_powershell_resolves_outlook_folders_before_command_arguments(self) -> None:
        script = _powershell_script()
        self.assertIn("$draftFolder = $namespace.GetDefaultFolder(16)", script)
        self.assertIn("$sentFolder = $namespace.GetDefaultFolder(5)", script)
        executable_lines = [
            line.strip()
            for line in script.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertFalse(
            any("-Folder $namespace.GetDefaultFolder(" in line for line in executable_lines)
        )

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
                stderr="RP_OUTLOOK_ERROR|stage=com",
            )

        with self.assertRaisesRegex(OutlookDraftTransportError, "Outlook"):
            create_outlook_drafts(
                [self.request()],
                runner=fake_runner,
                platform_name="nt",
            )

    def test_payload_failure_returns_specific_error(self) -> None:
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                11,
                stdout="",
                stderr="RP_OUTLOOK_ERROR|stage=payload",
            )

        with self.assertRaisesRegex(OutlookDraftTransportError, "temporaire"):
            create_outlook_drafts(
                [self.request()],
                runner=fake_runner,
                platform_name="nt",
            )

    def test_code_one_returns_compatibility_diagnostic(self) -> None:
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="ParserError")

        with self.assertRaisesRegex(OutlookDraftTransportError, "PowerShell"):
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
