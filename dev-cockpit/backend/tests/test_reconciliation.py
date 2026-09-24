import unittest

import httpx

from app.config import Settings
from app.github import GitHubClient
from app.roadmap import parse_cockpit_pipeline
from app.service import _reconcile_canonical_pipeline


PIPELINE = """
<!-- COCKPIT_PIPELINE_V1 -->
KEY | TYPE | STATUS | PARENT | LANE | TITLE
399C | WORK | DONE | #399 | MAIN | concurrence
399D | WORK | READY | #399 | MAIN | React + parcours navigateur
276 | WORK | BLOCKED | #276 | MAIN | routage approbation
408 | WORK | READY | #408 | PARALLEL | cycle de vie
<!-- /COCKPIT_PIPELINE_V1 -->
"""


def response(payload, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


class RoadmapReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def _reconcile(
        self,
        *,
        open_prs=None,
        closed_prs=None,
        files=None,
        pull_details=None,
        runs=None,
        jobs=None,
        contract_body: str = PIPELINE,
    ):
        open_prs = open_prs or []
        closed_prs = closed_prs or []
        files = files or {}
        pull_details = pull_details or {}
        runs = runs or {}
        jobs = jobs or {}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "/pulls/" in path and path.endswith("/files"):
                number = int(path.split("/")[-2])
                return response(files.get(number, []))
            if "/pulls/" in path:
                number = int(path.rsplit("/", 1)[-1])
                return response(pull_details[number])
            if path.endswith("/actions/runs"):
                sha = request.url.params.get("head_sha")
                return response({"workflow_runs": runs.get(sha, [])})
            if "/actions/runs/" in path and path.endswith("/jobs"):
                run_id = int(path.split("/")[-2])
                return response({"jobs": jobs.get(run_id, [])})
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
            return await _reconcile_canonical_pipeline(
                client,
                "tchi99/RessourcePlanner",
                pipeline_contract=parse_cockpit_pipeline(contract_body),
                open_raw=open_prs,
                closed_raw=closed_prs,
            )
        finally:
            await client.close()

    async def test_coherent_pipeline_has_no_findings_or_proposal(self):
        result = await self._reconcile()
        self.assertEqual(result["status"], "coherent")
        self.assertEqual(result["findings"], [])
        self.assertIsNone(result["proposal"])

    async def test_ready_merged_green_is_stale_and_promotes_next_main_step(self):
        raw = {
            "number": 423,
            "title": "feat(399D): React cancellation workflow",
            "body": "Refs #399D",
            "head": {"ref": "feat/399d-ui"},
            "merged_at": "2026-09-24T17:10:00Z",
        }
        details = {
            **raw,
            "state": "closed",
            "merged": True,
            "draft": False,
            "mergeable": None,
            "mergeable_state": "unknown",
            "html_url": "https://github.test/pull/423",
            "updated_at": "2026-09-24T17:10:00Z",
            "head": {"ref": "feat/399d-ui", "sha": "sha-399d"},
            "base": {"ref": "main"},
        }
        result = await self._reconcile(
            closed_prs=[raw],
            files={423: [{"filename": "frontend/src/App.tsx"}]},
            pull_details={423: details},
            runs={
                "sha-399d": [
                    {
                        "id": 910,
                        "name": "CI",
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.test/actions/runs/910",
                        "run_number": 910,
                    }
                ]
            },
            jobs={
                910: [
                    {
                        "id": 1,
                        "name": "tests",
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.test/jobs/1",
                    }
                ]
            },
        )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["findings"][0]["code"], "ready_merged_green")
        proposal = result["proposal"]
        self.assertIsNotNone(proposal)
        self.assertEqual(
            proposal["changes"],
            [
                {"key": "399D", "from": "READY", "to": "DONE"},
                {"key": "276", "from": "BLOCKED", "to": "READY"},
            ],
        )
        self.assertIn(
            "399D | WORK | DONE | #399 | MAIN | React + parcours navigateur",
            proposal["pipeline_block"],
        )
        self.assertIn(
            "276 | WORK | READY | #276 | MAIN | routage approbation",
            proposal["pipeline_block"],
        )

    async def test_other_slice_pr_mentioning_ready_slice_is_not_delivery_evidence(self):
        raw = {
            "number": 417,
            "title": "test(399C): harden cancellation concurrency",
            "body": "Refs #399C\n\nAucun changement React : 399D reste hors périmètre.",
            "head": {"ref": "test/399c-cancellation-concurrency"},
            "merged_at": "2026-09-24T12:51:23Z",
        }
        result = await self._reconcile(
            closed_prs=[raw],
            files={417: [{"filename": "tests/test_demand_cancellation_request.py"}]},
        )

        self.assertEqual(result["status"], "coherent")
        self.assertEqual(result["findings"], [])
        self.assertIsNone(result["proposal"])

    async def test_ready_merged_red_does_not_propose_promotion(self):
        raw = {
            "number": 423,
            "title": "feat(399D): React cancellation workflow",
            "body": "Refs #399D",
            "head": {"ref": "feat/399d-ui"},
            "merged_at": "2026-09-24T17:10:00Z",
        }
        details = {
            **raw,
            "state": "closed",
            "merged": True,
            "draft": False,
            "mergeable": None,
            "mergeable_state": "unknown",
            "html_url": "https://github.test/pull/423",
            "updated_at": "2026-09-24T17:10:00Z",
            "head": {"ref": "feat/399d-ui", "sha": "sha-399d"},
            "base": {"ref": "main"},
        }
        result = await self._reconcile(
            closed_prs=[raw],
            files={423: [{"filename": "frontend/src/App.tsx"}]},
            pull_details={423: details},
            runs={
                "sha-399d": [
                    {
                        "id": 911,
                        "name": "CI",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://github.test/actions/runs/911",
                        "run_number": 911,
                    }
                ]
            },
            jobs={911: []},
        )

        self.assertEqual(result["status"], "attention")
        self.assertEqual(result["findings"][0]["code"], "ready_merged_unverified")
        self.assertIsNone(result["proposal"])

    async def test_docs_only_merged_pr_is_not_delivery_evidence(self):
        raw = {
            "number": 423,
            "title": "docs(399D): document UI workflow",
            "body": "Refs #399D",
            "head": {"ref": "docs/399d"},
            "merged_at": "2026-09-24T17:10:00Z",
        }
        result = await self._reconcile(
            closed_prs=[raw],
            files={423: [{"filename": "docs/architecture/ADR-010.md"}]},
        )

        self.assertEqual(result["status"], "coherent")
        self.assertEqual(result["findings"], [])
        self.assertIsNone(result["proposal"])

    async def test_future_blocked_step_with_open_pr_is_attention_only(self):
        raw = {
            "number": 424,
            "title": "feat(276): approval routing",
            "body": "Refs #276",
            "head": {"ref": "feat/276-routing"},
            "merged_at": None,
        }
        details = {
            **raw,
            "state": "open",
            "merged": False,
            "draft": False,
            "mergeable": True,
            "mergeable_state": "clean",
            "html_url": "https://github.test/pull/424",
            "updated_at": "2026-09-24T17:15:00Z",
            "head": {"ref": "feat/276-routing", "sha": "sha-276"},
            "base": {"ref": "main"},
        }
        result = await self._reconcile(
            open_prs=[raw],
            files={424: [{"filename": "app/application/approval.py"}]},
            pull_details={424: details},
            runs={"sha-276": []},
        )

        self.assertEqual(result["status"], "attention")
        self.assertEqual(result["findings"][0]["code"], "blocked_open_pr")
        self.assertEqual(result["findings"][0]["key"], "276")
        self.assertIsNone(result["proposal"])

    async def test_invalid_pipeline_short_circuits_without_github_calls(self):
        invalid = """
<!-- COCKPIT_PIPELINE_V1 -->
KEY | TYPE | STATUS | PARENT | LANE | TITLE
399D | WORK | READY | #399 | MAIN | UI
276 | WORK | READY | #276 | MAIN | approval
<!-- /COCKPIT_PIPELINE_V1 -->
"""
        result = await self._reconcile(contract_body=invalid)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["findings"], [])
        self.assertIsNone(result["proposal"])


if __name__ == "__main__":
    unittest.main()
