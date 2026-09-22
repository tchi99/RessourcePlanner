from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator


HeartbeatState = Literal["working", "idle"]
EffectiveState = Literal["working", "idle", "possible_stall", "disconnected"]
DEFAULT_STALE_SECONDS = 30


def normalize_chat_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in {"chatgpt.com", "www.chatgpt.com"}:
        raise ValueError("conversation_url doit pointer vers https://chatgpt.com/.")
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", "chatgpt.com", path, "", ""))


class ChatHeartbeat(BaseModel):
    conversation_url: str = Field(min_length=1, max_length=2048)
    state: HeartbeatState
    page_visible: bool = True
    page_focused: bool = True
    ui_signal: Literal["stop-control", "none"] = "none"

    @field_validator("conversation_url")
    @classmethod
    def validate_conversation_url(cls, value: str) -> str:
        return normalize_chat_url(value)


class ChatStatusStore:
    def __init__(self, *, stale_seconds: int = DEFAULT_STALE_SECONDS):
        self._stale_seconds = stale_seconds
        self._lock = Lock()
        self._entries: dict[str, dict[str, object]] = {}

    def heartbeat(
        self,
        payload: ChatHeartbeat,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current = now or datetime.now(timezone.utc)
        with self._lock:
            existing = self._entries.get(payload.conversation_url)
            working_since = None
            last_completed_at = existing.get("last_completed_at") if existing else None
            if payload.state == "working":
                if existing and existing.get("state") == "working":
                    working_since = existing.get("working_since")
                working_since = working_since or current
            elif existing and existing.get("state") == "working":
                last_completed_at = current
            self._entries[payload.conversation_url] = {
                "conversation_url": payload.conversation_url,
                "state": payload.state,
                "page_visible": payload.page_visible,
                "page_focused": payload.page_focused,
                "ui_signal": payload.ui_signal,
                "last_seen": current,
                "working_since": working_since,
                "last_completed_at": last_completed_at,
            }
        return self._serialize(payload.conversation_url, current)

    def snapshot(self, *, now: datetime | None = None) -> dict[str, object]:
        current = now or datetime.now(timezone.utc)
        with self._lock:
            urls = list(self._entries)
        return {
            "stale_after_seconds": self._stale_seconds,
            "conversations": [self._serialize(url, current) for url in urls],
        }

    def _serialize(self, url: str, now: datetime) -> dict[str, object]:
        with self._lock:
            entry = dict(self._entries[url])
        last_seen = entry["last_seen"]
        assert isinstance(last_seen, datetime)
        age_seconds = max(0, int((now - last_seen).total_seconds()))
        connected = age_seconds <= self._stale_seconds
        raw_state = str(entry["state"])
        if connected:
            effective_state: EffectiveState = (
                "working" if raw_state == "working" else "idle"
            )
        elif raw_state == "working":
            effective_state = "possible_stall"
        else:
            effective_state = "disconnected"

        working_since = entry.get("working_since")
        last_completed_at = entry.get("last_completed_at")
        last_completed_seconds = (
            max(0, int((now - last_completed_at).total_seconds()))
            if isinstance(last_completed_at, datetime)
            else None
        )
        return {
            "conversation_url": url,
            "state": raw_state,
            "effective_state": effective_state,
            "connected": connected,
            "page_visible": bool(entry["page_visible"]),
            "page_focused": bool(entry["page_focused"]),
            "ui_signal": entry["ui_signal"],
            "last_seen_at": last_seen.isoformat(),
            "last_seen_seconds": age_seconds,
            "working_since": (
                working_since.isoformat()
                if isinstance(working_since, datetime)
                else None
            ),
            "last_completed_at": (
                last_completed_at.isoformat()
                if isinstance(last_completed_at, datetime)
                else None
            ),
            "last_completed_seconds": last_completed_seconds,
        }
