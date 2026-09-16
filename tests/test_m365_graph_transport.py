from __future__ import annotations

import json
import unittest

import httpx

from app.application.communications import CommunicationTransportMessage
from app.application.errors import ApplicationUnavailableError
from app.infrastructure.m365 import (
    MicrosoftGraphCommunicationSettings,
    MicrosoftGraphCommunicationTransport,
)


class MicrosoftGraphCommunicationTransportTests(unittest.TestCase):
    def _settings(self) -> MicrosoftGraphCommunicationSettings:
        return MicrosoftGraphCommunicationSettings(
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="super-secret",
            mailbox="planning@example.test",
        )

    @staticmethod
    def _message(address: str) -> CommunicationTransportMessage:
        return CommunicationTransportMessage(
            audience="technician",
            recipient_id=f"resource:{address}",
            recipient_email=address,
            subject="Planning semaine prochaine",
            body="Bonjour\nVoici votre planning.",
        )

    def test_create_drafts_uses_app_only_token_and_never_calls_send(self) -> None:
        requests: list[httpx.Request] = []
        draft_number = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal draft_number
            requests.append(request)
            if request.url.path.endswith("/oauth2/v2.0/token"):
                body = request.content.decode("utf-8")
                self.assertIn("grant_type=client_credentials", body)
                self.assertIn("scope=https%3A%2F%2Fgraph.microsoft.com%2F.default", body)
                return httpx.Response(200, json={"access_token": "test-token"})
            if request.method == "POST" and request.url.path.endswith("/users/planning@example.test/messages"):
                draft_number += 1
                payload = json.loads(request.content)
                self.assertEqual(payload["body"]["contentType"], "Text")
                self.assertTrue(payload["toRecipients"][0]["emailAddress"]["address"].endswith("@example.test"))
                self.assertEqual(request.headers["Authorization"], "Bearer test-token")
                return httpx.Response(201, json={"id": f"draft-{draft_number}"})
            self.fail(f"Requête Graph inattendue: {request.method} {request.url}")

        adapter = MicrosoftGraphCommunicationTransport(
            self._settings(),
            transport=httpx.MockTransport(handler),
        )
        result = adapter.create_drafts(
            (self._message("tech1@example.test"), self._message("tech2@example.test"))
        )

        self.assertEqual(result.provider, "microsoft_graph")
        self.assertEqual(result.created_count, 2)
        self.assertEqual(sum("/messages" in request.url.path for request in requests), 2)
        self.assertFalse(any(request.url.path.endswith("/send") for request in requests))

    def test_partial_failure_attempts_to_delete_drafts_already_created(self) -> None:
        draft_posts = 0
        deleted: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal draft_posts
            if request.url.path.endswith("/oauth2/v2.0/token"):
                return httpx.Response(200, json={"access_token": "test-token"})
            if request.method == "POST" and request.url.path.endswith("/messages"):
                draft_posts += 1
                if draft_posts == 1:
                    return httpx.Response(201, json={"id": "draft-1"})
                return httpx.Response(503, json={"error": {"code": "ServiceUnavailable"}})
            if request.method == "DELETE":
                deleted.append(request.url.path)
                return httpx.Response(204)
            self.fail(f"Requête Graph inattendue: {request.method} {request.url}")

        adapter = MicrosoftGraphCommunicationTransport(
            self._settings(),
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(ApplicationUnavailableError) as caught:
            adapter.create_drafts(
                (self._message("tech1@example.test"), self._message("tech2@example.test"))
            )

        self.assertEqual(caught.exception.code, "communication_graph_request_failed")
        self.assertEqual(len(deleted), 1)
        self.assertTrue(deleted[0].endswith("/messages/draft-1"))

    def test_settings_repr_never_exposes_client_secret(self) -> None:
        settings = self._settings()
        self.assertNotIn("super-secret", repr(settings))


if __name__ == "__main__":
    unittest.main()
