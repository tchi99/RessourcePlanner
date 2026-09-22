from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from app.chat_status import ChatHeartbeat, ChatStatusStore, normalize_chat_url


class ChatStatusTests(unittest.TestCase):
    def test_normalize_chat_url_strips_query_and_fragment(self):
        self.assertEqual(
            normalize_chat_url("https://www.chatgpt.com/c/example/?model=test#part"),
            "https://chatgpt.com/c/example",
        )

    def test_working_heartbeat_becomes_possible_stall_when_stale(self):
        store = ChatStatusStore(stale_seconds=30)
        start = datetime(2026, 9, 22, 20, 0, tzinfo=timezone.utc)
        payload = ChatHeartbeat(
            conversation_url="https://chatgpt.com/c/example",
            state="working",
            page_visible=True,
            page_focused=True,
            ui_signal="stop-control",
        )

        current = store.heartbeat(payload, now=start)
        self.assertEqual(current["effective_state"], "working")
        self.assertTrue(current["connected"])

        snapshot = store.snapshot(now=start + timedelta(seconds=31))
        row = snapshot["conversations"][0]
        self.assertEqual(row["effective_state"], "possible_stall")
        self.assertFalse(row["connected"])
        self.assertEqual(row["last_seen_seconds"], 31)

    def test_working_to_idle_records_completion_time(self):
        store = ChatStatusStore(stale_seconds=30)
        start = datetime(2026, 9, 22, 20, 0, tzinfo=timezone.utc)
        store.heartbeat(
            ChatHeartbeat(
                conversation_url="https://chatgpt.com/c/example",
                state="working",
                ui_signal="stop-control",
            ),
            now=start,
        )
        completed = store.heartbeat(
            ChatHeartbeat(
                conversation_url="https://chatgpt.com/c/example",
                state="idle",
            ),
            now=start + timedelta(seconds=8),
        )
        self.assertEqual(completed["effective_state"], "idle")
        self.assertEqual(completed["last_completed_seconds"], 0)
        self.assertIsNotNone(completed["last_completed_at"])

    def test_idle_heartbeat_becomes_disconnected_when_stale(self):
        store = ChatStatusStore(stale_seconds=10)
        start = datetime(2026, 9, 22, 20, 0, tzinfo=timezone.utc)
        store.heartbeat(
            ChatHeartbeat(
                conversation_url="https://chatgpt.com/c/example",
                state="idle",
                page_visible=False,
                page_focused=False,
            ),
            now=start,
        )
        row = store.snapshot(now=start + timedelta(seconds=11))["conversations"][0]
        self.assertEqual(row["effective_state"], "disconnected")

    def test_rejects_non_chatgpt_url(self):
        with self.assertRaises(ValueError):
            normalize_chat_url("https://example.com/c/example")


if __name__ == "__main__":
    unittest.main()
