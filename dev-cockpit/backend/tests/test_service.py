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



PIPELINE_ROADMAP_DONE_333 = """
**#332 est terminé. #333 est la tranche produit active.**

Ordre actif :

1. **#333 — extension de fenêtre contrôlée**
   - ✅ **333A — décision contextuelle**
   - ✅ **333B — proposition hors enveloppe**
   - ✅ **333C — dialogue React + acceptation**

### Suite produit après #333 — bloc P1 puis préparation environnementale

Chemin principal retenu :

```text
#333A → #333B → #333C
  ↓
ASTRA ciblé #901 sur main post-#333
  ↓
#901 actifs réservables
  ↓
#902 qualifications
  ↓
#903 validation VM Ubuntu réelle avec SQLite
```

**Gates et logique :**

| Étape | État / gate | Pourquoi maintenant |
|---|---|---|
| #333 | terminé | bloc DEV stabilisé |
| analyse ASTRA #901 | après fusion complète de #333 | vérifier l'architecture |
| #901 | NEXT après analyse | travail DEV |
| #902 | après #901 | travail DEV |
| #903 | après P1 ou en parallèle infra | valider la vraie VM Ubuntu |
"""



ROADMAP_291_READY = """
**L'analyse ASTRA est terminée. La prochaine tranche active est #291, avec 291A READY.**

Ordre actif :

1. **#291 — ressources réservables non humaines — ACTIF**
   - **291A — contrats et frontières pures — READY**
   - **291B — catalogue et persistance**
   - **291C — demande, approbation et matérialisation**
   - **291D — réservations et concurrence**
   - **291E — projections et delta**
   - **291F — React et acceptation**
"""

ISSUE_291_READY = """
# #291 — ressources réservables non humaines

Analyse ASTRA terminée. ADR-007 accepté via une PR documentaire avant DEV.

## Découpage d'implémentation

Ordre obligatoire : **291A → 291B → 291C → 291D → 291E → 291F**.

### #291A — contrats et frontières pures — READY
### #291B — catalogue et persistance
### #291C — demande, approbation et matérialisation
### #291D — réservations et concurrence
### #291E — projections et delta
### #291F — React et acceptation
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
            if path.startswith("/repos/tchi99/RessourcePlanner/pulls/") and path.endswith("/files"):
                return response([
                    {"filename": "app/domain/implementation.py", "status": "modified"}
                ])
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


    async def _pipeline_dashboard(self, *, gate_done: bool):
        roadmap_body = PIPELINE_ROADMAP_DONE_333
        if gate_done:
            roadmap_body = roadmap_body.replace(
                "| analyse ASTRA #901 | après fusion complète de #333 |",
                "| analyse ASTRA #901 | ✅ terminée |",
            )

        issue_body = """
# #333 — extension de fenêtre contrôlée
### ✅ #333A — décision contextuelle
### ✅ #333B — proposition hors enveloppe
### ✅ #333C — dialogue React + acceptation
"""

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            query = dict(request.url.params)
            if path == "/repos/tchi99/RessourcePlanner/issues/55":
                return response({
                    "number": 55,
                    "title": "Roadmap maître",
                    "body": roadmap_body,
                    "html_url": "https://github.test/issues/55",
                    "updated_at": "2026-09-23T01:00:00Z",
                    "state": "open",
                })
            if path == "/repos/tchi99/RessourcePlanner/issues/333":
                return response({
                    "number": 333,
                    "title": "Extension de fenêtre",
                    "body": issue_body,
                    "state": "open",
                    "html_url": "https://github.test/issues/333",
                    "updated_at": "2026-09-23T01:00:00Z",
                })
            if path == "/repos/tchi99/RessourcePlanner/pulls":
                return response([])
            if path == "/repos/tchi99/RessourcePlanner/commits":
                return response([{
                    "sha": "main-pipeline",
                    "html_url": "https://github.test/commit/main-pipeline",
                    "commit": {
                        "message": "main",
                        "author": {"date": "2026-09-23T00:59:00Z"},
                    },
                }])
            if path == "/repos/tchi99/RessourcePlanner/contents/AGENTS.md":
                return response(encoded_file(AGENTS))
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture":
                return response([])
            if path == "/repos/tchi99/RessourcePlanner/branches":
                return response([{"name": "main", "commit": {"sha": "main-pipeline"}}])
            if path.startswith("/repos/tchi99/RessourcePlanner/issues/"):
                number = int(path.rsplit("/", 1)[-1])
                return response({
                    "number": number,
                    "title": f"Issue {number}",
                    "body": "",
                    "state": "open",
                    "html_url": f"https://github.test/issues/{number}",
                    "updated_at": "2026-09-23T01:00:00Z",
                })
            if path == "/repos/tchi99/RessourcePlanner/actions/runs":
                return response({"workflow_runs": []})
            raise AssertionError(f"Unexpected request: {request.method} {request.url} {query}")

        settings = Settings(
            github_token="test",
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

    async def test_architecture_gate_stops_dev_prompt_after_completed_block(self):
        dashboard = await self._pipeline_dashboard(gate_done=False)
        self.assertTrue(dashboard["active_work"]["block_done"])
        self.assertEqual(dashboard["pipeline"]["now"]["kind"], "ARCHITECTURE_GATE")
        self.assertEqual(dashboard["pipeline"]["now"]["issue_number"], 901)
        self.assertIn("Gate d'architecture requise", dashboard["next_action"])
        self.assertIn("Aucune tranche DEV", dashboard["dev_prompt"])
        self.assertIn("ne l'exécute pas comme une tranche", dashboard["dev_prompt"])
        self.assertNotIn("Démarrer/reprendre", dashboard["dev_prompt"])

    async def test_satisfied_architecture_gate_releases_next_work_prompt(self):
        dashboard = await self._pipeline_dashboard(gate_done=True)
        self.assertEqual(dashboard["pipeline"]["now"]["key"], "901")
        self.assertEqual(dashboard["pipeline"]["now"]["kind"], "WORK")
        self.assertIn("Prochaine tranche DEV du pipeline", dashboard["next_action"])
        self.assertIn("prochain travail DEV", dashboard["dev_prompt"])


    async def _dashboard_291_with_architecture_pr(self, *, merged: bool):
        pr = {
            "number": 392,
            "title": "docs: add architecture ADR for reservable assets",
            "body": "Architecture analysis for #291 completed before 291A. No business code is modified.",
            "html_url": "https://github.test/pull/392",
            "merged_at": "2026-09-23T14:17:04Z" if merged else None,
            "updated_at": "2026-09-23T14:17:04Z",
            "state": "closed" if merged else "open",
            "draft": False,
            "mergeable": True,
            "mergeable_state": "clean",
            "head": {"ref": "docs/291-architecture", "sha": "docs392"},
            "base": {"ref": "main"},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            query = dict(request.url.params)
            if path == "/repos/tchi99/RessourcePlanner/issues/55":
                return response({
                    "number": 55,
                    "title": "Roadmap maître",
                    "body": ROADMAP_291_READY,
                    "html_url": "https://github.test/issues/55",
                    "updated_at": "2026-09-23T14:18:00Z",
                    "state": "open",
                })
            if path == "/repos/tchi99/RessourcePlanner/issues/291":
                return response({
                    "number": 291,
                    "title": "Ressources réservables",
                    "body": ISSUE_291_READY,
                    "state": "open",
                    "html_url": "https://github.test/issues/291",
                    "updated_at": "2026-09-23T14:18:00Z",
                })
            if path == "/repos/tchi99/RessourcePlanner/pulls":
                state = query.get("state")
                if merged:
                    return response([pr] if state == "closed" else [])
                return response([pr] if state == "open" else [])
            if path == "/repos/tchi99/RessourcePlanner/pulls/392":
                return response(pr)
            if path == "/repos/tchi99/RessourcePlanner/pulls/392/files":
                return response([
                    {
                        "filename": "docs/architecture/ADR-099-reservable-assets.md",
                        "status": "added",
                    },
                    {
                        "filename": "docs/architecture/README.md",
                        "status": "modified",
                    },
                ])
            if path == "/repos/tchi99/RessourcePlanner/actions/runs":
                return response({"workflow_runs": []})
            if path == "/repos/tchi99/RessourcePlanner/commits":
                return response([{
                    "sha": "main291",
                    "html_url": "https://github.test/commit/main291",
                    "commit": {
                        "message": "main",
                        "author": {"date": "2026-09-23T14:18:00Z"},
                    },
                }])
            if path == "/repos/tchi99/RessourcePlanner/contents/AGENTS.md":
                return response(encoded_file(AGENTS))
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture":
                return response([])
            if path == "/repos/tchi99/RessourcePlanner/branches":
                return response([{"name": "main", "commit": {"sha": "main291"}}])
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
            return await build_dashboard(client, settings, "tchi99/RessourcePlanner")
        finally:
            await client.close()

    async def test_open_architecture_docs_pr_is_not_dev_work(self):
        dashboard = await self._dashboard_291_with_architecture_pr(merged=False)

        self.assertEqual(dashboard["active_work"]["subitem_key"], "291A")
        self.assertIsNone(dashboard["active_work"]["primary_pr"])
        self.assertEqual(dashboard["open_prs"][0]["number"], 392)
        self.assertIn("Démarrer/reprendre 291A", dashboard["next_action"])
        self.assertIn(
            "291A → 291B → 291C → 291D → 291E → 291F",
            dashboard["dev_prompt"],
        )

    async def test_merged_architecture_docs_pr_does_not_block_ready_dev_slice(self):
        dashboard = await self._dashboard_291_with_architecture_pr(merged=True)

        self.assertEqual(dashboard["active_work"]["subitem_key"], "291A")
        self.assertIsNone(dashboard["active_work"]["merged_but_unmarked_pr"])
        self.assertNotIn("fusionnée, mais la tranche", dashboard["dev_prompt"])
        self.assertIn("Démarrer/reprendre 291A", dashboard["next_action"])
        self.assertIn(
            "291A → 291B → 291C → 291D → 291E → 291F",
            dashboard["dev_prompt"],
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
