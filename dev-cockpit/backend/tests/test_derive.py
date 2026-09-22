import unittest
from datetime import datetime, timezone

from app.derive import build_next_action_and_prompt, derive_states


class DeriveTests(unittest.TestCase):
    def test_red_ci_becomes_stalled_after_configured_minutes(self):
        pr = {
            "number": 401,
            "state": "open",
            "mergeable": True,
            "runs": [
                {
                    "status": "completed",
                    "conclusion": "failure",
                    "updated_at": "2026-09-22T14:42:00Z",
                    "jobs": [
                        {"name": "Python verification (shard 1)", "status": "completed", "conclusion": "failure"},
                        {"name": "frontend-validation", "status": "completed", "conclusion": "success"},
                    ],
                }
            ],
        }
        result = derive_states(
            block_done=False,
            primary_pr=pr,
            active_branch={"name": "issue-13c", "sha": "abc"},
            active_commit_date="2026-09-22T14:35:00Z",
            stalled_after_minutes=15,
            now=datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc),
        )
        self.assertIn("CI_RED", result["states"])
        self.assertIn("STALLED", result["states"])
        self.assertEqual(result["failed_jobs"], ["Python verification (shard 1)"])
        self.assertEqual(result["stalled_details"]["ci_failed_minutes"], 18)
        self.assertTrue(result["stalled_details"]["no_new_commit"])
        self.assertTrue(result["stalled_details"]["no_active_workflow"])

    def test_new_commit_after_failure_prevents_stalled(self):
        pr = {
            "number": 401,
            "state": "open",
            "runs": [{"status": "completed", "conclusion": "failure", "updated_at": "2026-09-22T14:20:00Z", "jobs": []}],
        }
        result = derive_states(
            block_done=False,
            primary_pr=pr,
            active_branch={"name": "issue-13c", "sha": "abc"},
            active_commit_date="2026-09-22T14:45:00Z",
            stalled_after_minutes=10,
            now=datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc),
        )
        self.assertNotIn("STALLED", result["states"])
        self.assertFalse(result["stalled"])

    def test_ready_prompt_includes_issue_adrs_and_authorized_chaining(self):
        derived = {"stalled": False, "ci_red": False, "ci_running": False, "failed_jobs": [], "states": ["READY"]}
        _, prompt = build_next_action_and_prompt(
            parent_issue=13,
            active_key="13A",
            block_done=False,
            can_chain_block=True,
            primary_pr=None,
            active_branch=None,
            derived=derived,
            roadmap_issue=55,
        )
        self.assertIn("Continue #13 à partir de 13A", prompt)
        self.assertIn("Consulte l'issue #13 et les ADR applicables", prompt)
        self.assertIn("Enchaîne autonomement les tranches restantes du bloc #13", prompt)

    def test_red_ci_prompt_reuses_current_pr(self):
        derived = {"stalled": True, "ci_red": True, "ci_running": False, "failed_jobs": ["Python shard 1"], "states": ["IN_PROGRESS", "CI_RED", "STALLED"]}
        _, prompt = build_next_action_and_prompt(
            parent_issue=13,
            active_key="13C",
            block_done=False,
            can_chain_block=True,
            primary_pr={"number": 401},
            active_branch={"name": "issue-13c"},
            derived=derived,
            roadmap_issue=55,
        )
        self.assertIn("Reprends 13C depuis la PR #401 actuelle", prompt)
        self.assertIn("La CI est rouge", prompt)
        self.assertIn("poursuis ensuite #13", prompt)

    def test_completed_block_prompt_asks_to_verify_next_ready(self):
        _, prompt = build_next_action_and_prompt(
            parent_issue=13,
            active_key=None,
            block_done=True,
            can_chain_block=False,
            primary_pr=None,
            active_branch=None,
            derived={"states": ["DONE"]},
            roadmap_issue=55,
        )
        self.assertIn("Le bloc #13 semble terminé", prompt)
        self.assertIn("détermine le prochain item READY", prompt)


if __name__ == "__main__":
    unittest.main()
