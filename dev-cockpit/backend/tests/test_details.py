import base64
import unittest

import httpx

from app.config import Settings
from app.details import (
    build_architecture_detail,
    build_commit_detail,
    build_issue_detail,
    build_roadmap_detail,
    markdown_sections,
)
from app.github import GitHubClient


def response(data, status=200):
    return httpx.Response(status, json=data)


def encoded_file(text):
    return {
        "encoding": "base64",
        "content": base64.b64encode(text.encode()).decode(),
    }


ISSUE_BODY = """# #332 — partage et duplication

## Objectif

Préserver les invariants.

### 🟡 #332A — contrat pur

Livrables:
- un contrat;
- des tests.

Voir ADR-004 et docs/architecture/ADR-004-candidate-approval-and-active-plan.md.

#### Critères

- aucun double comptage.

### #332B — runtime

Deuxième tranche.
"""

ROADMAP_BODY = """# Roadmap

Ordre actif :

1. **#332 — partage et duplication**
2. **#333 — actions de masse**
"""


class DetailProjectionTests(unittest.IsolatedAsyncioTestCase):
    def settings(self) -> Settings:
        return Settings(
            github_token="test",
            repository="tchi99/RessourcePlanner",
            roadmap_issue=55,
            github_api_url="https://api.github.test",
        )

    async def with_client(self, handler, callback):
        client = GitHubClient(
            self.settings(),
            transport=httpx.MockTransport(handler),
        )
        try:
            return await callback(client)
        finally:
            await client.close()

    def test_markdown_sections_capture_nested_subitem_body(self):
        sections = markdown_sections(ISSUE_BODY)
        section = next(row for row in sections if row["work_key"] == "332A")
        self.assertEqual(section["level"], 3)
        self.assertIn("Livrables", section["content"])
        self.assertIn("#### Critères", section["content"])
        self.assertNotIn("Deuxième tranche", section["content"])

    async def test_issue_detail_includes_full_body_sections_and_referenced_adr(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/repos/tchi99/RessourcePlanner/issues/332":
                return response(
                    {
                        "number": 332,
                        "title": "Partage",
                        "state": "open",
                        "body": ISSUE_BODY,
                        "html_url": "https://github.test/issues/332",
                        "updated_at": "2026-09-22T20:00:00Z",
                    }
                )
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture":
                return response(
                    [
                        {
                            "name": "ADR-004-candidate-approval-and-active-plan.md",
                            "path": "docs/architecture/ADR-004-candidate-approval-and-active-plan.md",
                            "type": "file",
                            "html_url": "https://github.test/adr4",
                        }
                    ]
                )
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture/ADR-004-candidate-approval-and-active-plan.md":
                return response(encoded_file("# ADR-004 — Candidate\n\n## Decision\n\nKeep them separate."))
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        async def callback(client):
            return await build_issue_detail(client, "tchi99/RessourcePlanner", 332)

        detail = await self.with_client(handler, callback)
        self.assertEqual(detail["number"], 332)
        self.assertEqual(
            next(row for row in detail["sections"] if row["work_key"] == "332A")["title"],
            "🟡 #332A — contrat pur",
        )
        self.assertEqual(len(detail["documents"]), 1)
        self.assertEqual(
            detail["documents"][0]["name"],
            "ADR-004-candidate-approval-and-active-plan.md",
        )

    async def test_commit_detail_lists_files_and_reads_changed_docs_at_sha(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/repos/tchi99/RessourcePlanner/commits/abc123":
                return response(
                    {
                        "sha": "abc123",
                        "html_url": "https://github.test/commit/abc123",
                        "commit": {
                            "message": "Implement 332A",
                            "author": {
                                "name": "Dev",
                                "date": "2026-09-22T20:00:00Z",
                            },
                        },
                        "stats": {"additions": 10, "deletions": 2, "total": 12},
                        "files": [
                            {
                                "filename": "app/domain/example.py",
                                "status": "modified",
                                "additions": 7,
                                "deletions": 2,
                                "changes": 9,
                                "blob_url": "https://github.test/blob/code",
                            },
                            {
                                "filename": "docs/architecture/ADR-004-example.md",
                                "status": "modified",
                                "additions": 3,
                                "deletions": 0,
                                "changes": 3,
                                "blob_url": "https://github.test/blob/doc",
                            },
                        ],
                    }
                )
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture/ADR-004-example.md":
                self.assertEqual(request.url.params.get("ref"), "abc123")
                return response(encoded_file("# ADR-004 example\n\nUpdated docs."))
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        async def callback(client):
            return await build_commit_detail(client, "tchi99/RessourcePlanner", "abc123")

        detail = await self.with_client(handler, callback)
        self.assertEqual(detail["stats"]["total"], 12)
        self.assertEqual(len(detail["files"]), 2)
        self.assertEqual(len(detail["documentation"]), 1)

    async def test_architecture_detail_reads_readme_and_adrs(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture":
                return response(
                    [
                        {
                            "name": "ADR-001-test.md",
                            "path": "docs/architecture/ADR-001-test.md",
                            "type": "file",
                            "html_url": "https://github.test/adr1",
                        },
                        {
                            "name": "README.md",
                            "path": "docs/architecture/README.md",
                            "type": "file",
                            "html_url": "https://github.test/readme",
                        },
                    ]
                )
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture/README.md":
                return response(encoded_file("# Architecture\n\nVue générale."))
            if path == "/repos/tchi99/RessourcePlanner/contents/docs/architecture/ADR-001-test.md":
                return response(encoded_file("# ADR-001 — Test\n\n**Status:** Accepted\n\nDecision."))
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        async def callback(client):
            return await build_architecture_detail(client, "tchi99/RessourcePlanner")

        detail = await self.with_client(handler, callback)
        self.assertEqual(detail["documents"][0]["name"], "README.md")
        self.assertEqual(detail["documents"][1]["status"], "Accepted")

    async def test_roadmap_detail_returns_all_top_level_items(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/repos/tchi99/RessourcePlanner/issues/55":
                return response(
                    {
                        "number": 55,
                        "title": "Roadmap",
                        "state": "open",
                        "body": ROADMAP_BODY,
                        "html_url": "https://github.test/issues/55",
                        "updated_at": "2026-09-22T20:00:00Z",
                    }
                )
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        async def callback(client):
            return await build_roadmap_detail(
                client,
                self.settings(),
                "tchi99/RessourcePlanner",
            )

        detail = await self.with_client(handler, callback)
        self.assertEqual([item["key"] for item in detail["items"]], ["332", "333"])


if __name__ == "__main__":
    unittest.main()
