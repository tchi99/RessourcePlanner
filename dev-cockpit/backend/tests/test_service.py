import base64
import json
import unittest

import httpx

from app.config import Settings
from app.github import GitHubClient
from app.service import build_dashboard

ROADMAP_BODY = """
# Roadmap maître

**#331 est terminé. #13 est maintenant la tranche active, découpée en 13A→13H.**

Ordre actif :

1. **#331 — séparation des ressources**
   **Bloc terminé : 331A ✅ → 331E ✅.** #331 est désormais complétée.

2. **#13 — périodes + enveloppe approuvée commune**
   - **13A — contrat et politique pure**
   - **13B — révisions approuvées immuables**
   - **13C — préparation commune**

   Ordre : **13A → 13B → 13C**.

3. **#328 — identité canonique du demandeur**
"""

ISSUE_BODY = """
# #13 — périodes + enveloppe approuvée commune

Décisions architecturales documentées dans ADR-002 et ADR-003.

## Découpage d'implémentation

Ordre obligatoire :

### #13A — contrat et politique pure
### #13B — capture des révisions approuvées
### #13C — préparation commune et protection des verrous
"""

AGENTS = """
## 20. Chained execution
Automatic chaining is allowed only when the next item belongs to the same approved work block.
"""


def response(data, status=200):
    return httpx.Response(status, json=data)


def encoded_file(text):
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def _dashboard(self, closed_pulls=None):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            query = dict(request.url.params)
            if path == "/repos/tchi99/RessourcePlanner/issues/55":
                return response({"number": 55, "title": "Roadmap maître", "body": ROADMAP_BODY, "html_url": "https://github.test/issues/55", "updated_at": "2026-09-22T15:00:00Z", "state": "open"})
            if path == "/repos/tchi99/RessourcePlanner/issues/13":
                return response({"number": 13, "title": "Périodes + enveloppe", "body": ISSUE_BODY, "state": "open", "html_url": "https://github.test/issues/13", "updated_at": "2026-09-22T15:00:00Z"})
            if path == "/repos/tchi99/RessourcePlanner/pulls" and query.get("state") == "open":
                return response([])
            if path == "/repos/tchi99/RessourcePlanner/pulls" and query.get("state") == "closed":
                return response(closed_pulls or [])
            if path == "/repos/tchi99/RessourcePlanner/commits":
                return response([{"sha": "def456", "html_url": "https://github.test/commit/def456", "commit": {"message": "main", "author": {"date": "2026-09-22T14:55:00Z"}}}])
            if path == "/repos/tchi99/RessourcePlanner/contents/AGENTS.md":
                return response(encoded_file(AGENTS))
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture":
                return response([
                    {"name": "ADR-001-other.md", "html_url": "https://github.test/adr1"},
                    {"name": "ADR-002-periods.md", "html_url": "https://github.test/adr2"},
                    {"name": "ADR-003-approval.md", "html_url": "https://github.test/adr3"},
                    {"name": "README.md", "html_url": "https://github.test/arch"},
                ])
            if path == "/repos/tchi99/RessourcePlanner/branches":
                return response([{"name": "main", "commit": {"sha": "def456"}}])
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        settings = Settings(
            github_token="secret-that-must-not-leak",
            repository="tchi99/RessourcePlanner",
            roadmap_issue=55,
            stalled_after_minutes=20,
            github_api_url="https://api.github.test",
        )
        client = GitHubClient(settings, transport=httpx.MockTransport(handler))
        try:
            return await build_dashboard(client, settings, "tchi99/RessourcePlanner")
        finally:
            await client.close()

    async def test_current_issue_resolves_first_ready_subitem_and_dynamic_adrs(self):
        dashboard = await self._dashboard()
        self.assertEqual(dashboard["roadmap"]["active_issue"], 13)
        self.assertEqual(dashboard["roadmap"]["effective_active"], "13A")
        self.assertEqual(dashboard["active_work"]["subitem_key"], "13A")
        self.assertTrue(dashboard["active_work"]["can_chain_block"])
        self.assertEqual(dashboard["active_work"]["remaining_subitems"], ["13A", "13B", "13C"])
        self.assertEqual(dashboard["architecture"]["referenced_adrs"], ["ADR-002-periods.md", "ADR-003-approval.md"])
        self.assertIn("Continue #13 à partir de 13A", dashboard["dev_prompt"])
        self.assertNotIn("secret-that-must-not-leak", json.dumps(dashboard))

    async def test_branch_without_pr_is_observed_for_silent_stall(self):
        issue_body = ISSUE_BODY.replace(
            "### #13A — contrat et politique pure",
            "### 🟡 #13A — contrat et politique pure",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            query = dict(request.url.params)
            if path == "/repos/tchi99/RessourcePlanner/issues/55":
                return response({"number": 55, "title": "Roadmap maître", "body": ROADMAP_BODY, "html_url": "https://github.test/issues/55", "updated_at": "2026-09-22T14:00:00Z", "state": "open"})
            if path == "/repos/tchi99/RessourcePlanner/issues/13":
                return response({"number": 13, "title": "Périodes + enveloppe", "body": issue_body, "state": "open", "html_url": "https://github.test/issues/13", "updated_at": "2026-09-22T14:00:00Z"})
            if path == "/repos/tchi99/RessourcePlanner/pulls":
                return response([])
            if path == "/repos/tchi99/RessourcePlanner/commits":
                return response([{"sha": "main456", "html_url": "https://github.test/commit/main456", "commit": {"message": "main", "author": {"date": "2026-09-22T14:05:00Z"}}}])
            if path == "/repos/tchi99/RessourcePlanner/commits/abc":
                return response({"sha": "abc", "html_url": "https://github.test/commit/abc", "commit": {"message": "13A work", "author": {"date": "2026-09-22T14:00:00Z"}}})
            if path == "/repos/tchi99/RessourcePlanner/actions/runs":
                self.assertEqual(query.get("head_sha"), "abc")
                return response({"workflow_runs": []})
            if path == "/repos/tchi99/RessourcePlanner/contents/AGENTS.md":
                return response(encoded_file(AGENTS))
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture":
                return response([])
            if path == "/repos/tchi99/RessourcePlanner/branches":
                return response([
                    {"name": "main", "commit": {"sha": "main456"}},
                    {"name": "issue-13a", "commit": {"sha": "abc"}},
                ])
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        settings = Settings(
            github_token="test",
            repository="tchi99/RessourcePlanner",
            roadmap_issue=55,
            stalled_after_minutes=20,
            github_api_url="https://api.github.test",
        )
        client = GitHubClient(settings, transport=httpx.MockTransport(handler))
        try:
            dashboard = await build_dashboard(client, settings, "tchi99/RessourcePlanner")
        finally:
            await client.close()

        self.assertTrue(dashboard["active_work"]["explicit_in_progress"])
        self.assertEqual(dashboard["active_work"]["active_branch"]["name"], "issue-13a")
        self.assertIsNone(dashboard["active_work"]["primary_pr"])
        self.assertIn("STALLED", dashboard["active_work"]["states"])
        self.assertIn("branche issue-13a", dashboard["dev_prompt"])

    async def test_active_branch_can_be_on_later_page_and_newest_match_wins(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            query = dict(request.url.params)
            if path == "/repos/tchi99/RessourcePlanner/issues/55":
                return response({
                    "number": 55,
                    "title": "Roadmap maître",
                    "body": ROADMAP_BODY,
                    "html_url": "https://github.test/issues/55",
                    "updated_at": "2026-09-22T23:30:00Z",
                    "state": "open",
                })
            if path == "/repos/tchi99/RessourcePlanner/issues/13":
                return response({
                    "number": 13,
                    "title": "Périodes + enveloppe",
                    "body": ISSUE_BODY,
                    "state": "open",
                    "html_url": "https://github.test/issues/13",
                    "updated_at": "2026-09-22T23:30:00Z",
                })
            if path == "/repos/tchi99/RessourcePlanner/pulls":
                return response([])
            if path == "/repos/tchi99/RessourcePlanner/commits":
                return response([{
                    "sha": "main456",
                    "html_url": "https://github.test/commit/main456",
                    "commit": {
                        "message": "main",
                        "author": {"date": "2026-09-22T23:31:00Z"},
                    },
                }])
            if path == "/repos/tchi99/RessourcePlanner/commits/old13a":
                return response({
                    "sha": "old13a",
                    "html_url": "https://github.test/commit/old13a",
                    "commit": {
                        "message": "old 13A work",
                        "author": {"date": "2026-09-22T22:00:00Z"},
                    },
                })
            if path == "/repos/tchi99/RessourcePlanner/commits/new13a":
                return response({
                    "sha": "new13a",
                    "html_url": "https://github.test/commit/new13a",
                    "commit": {
                        "message": "current 13A work",
                        "author": {"date": "2026-09-22T23:45:00Z"},
                    },
                })
            if path == "/repos/tchi99/RessourcePlanner/actions/runs":
                self.assertEqual(query.get("head_sha"), "new13a")
                return response({"workflow_runs": []})
            if path == "/repos/tchi99/RessourcePlanner/contents/AGENTS.md":
                return response(encoded_file(AGENTS))
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture":
                return response([])
            if path == "/repos/tchi99/RessourcePlanner/branches":
                page = int(query.get("page", "1"))
                if page == 1:
                    branches = [
                        {"name": f"archive-{index:03d}", "commit": {"sha": f"archive{index:03d}"}}
                        for index in range(99)
                    ]
                    branches.append(
                        {"name": "issue-13a-old", "commit": {"sha": "old13a"}}
                    )
                    return response(branches)
                if page == 2:
                    return response([
                        {"name": "issue-13a-current", "commit": {"sha": "new13a"}},
                    ])
                return response([])
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        settings = Settings(
            github_token="test",
            repository="tchi99/RessourcePlanner",
            roadmap_issue=55,
            stalled_after_minutes=20,
            github_api_url="https://api.github.test",
        )
        client = GitHubClient(settings, transport=httpx.MockTransport(handler))
        try:
            dashboard = await build_dashboard(client, settings, "tchi99/RessourcePlanner")
        finally:
            await client.close()

        self.assertEqual(
            dashboard["active_work"]["active_branch"]["name"],
            "issue-13a-current",
        )
        self.assertEqual(
            dashboard["active_work"]["last_commit"]["sha"],
            "new13a",
        )
        self.assertNotEqual(
            dashboard["active_work"]["last_commit"]["sha"],
            dashboard["latest_commit"]["sha"],
        )

    async def test_merged_pr_does_not_mark_unupdated_subitem_done(self):
        dashboard = await self._dashboard([
            {
                "number": 401,
                "title": "#13A — contrat et politique pure",
                "body": "Refs #13 #55",
                "html_url": "https://github.test/pull/401",
                "merged_at": "2026-09-22T15:05:00Z",
            }
        ])
        self.assertEqual(dashboard["roadmap"]["effective_active"], "13A")
        self.assertFalse(dashboard["active_work"]["block_done"])
        self.assertEqual(dashboard["active_work"]["merged_but_unmarked_pr"]["number"], 401)
        self.assertIn("n'est pas explicitement terminée", dashboard["dev_prompt"])


if __name__ == "__main__":
    unittest.main()
