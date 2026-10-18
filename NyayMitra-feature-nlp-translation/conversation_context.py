"""
Lightweight conversation context for the "What Happened?" flow.

Two screens talk to this service — incident analysis
(`POST /api/incident/analyze`) and the case companion
(`POST /api/case-companion/ask`) — and both may be called more than
once for the same conversation. This module remembers just enough
between those calls:

    conversation_id      an opaque id the client sends (or one we mint)
    messages             the short history of what was asked/answered
    current_intent       what the conversation is doing right now,
                         e.g. "incident_analysis" or "case_companion"
    incident_category    the category incident analysis last settled on
    known_facts          facts already established (dates, amounts,
                         identifiers) so a later call does not lose them

Deliberately *not* a database. It is an in-memory store behind one
small interface (`ConversationContextStore`), bounded in both the
number of conversations and the number of messages kept per
conversation, so it cannot grow without end. When persistence arrives
(Member 4's My Cases work, or a real store), only this class's
internals change: `get` / `create` / `update` are the whole contract,
and callers already go through them.

Thread safety: FastAPI runs these endpoints in a threadpool, so every
mutation happens under one lock.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

# Bounds. Generous for a chat-length exchange, small enough that a
# long-lived service cannot accumulate abandoned conversations.
MAX_CONVERSATIONS = 200
MAX_MESSAGES = 40
MAX_FACTS = 60

# How long a message text is kept. The endpoints already cap request
# sizes; this is the second belt, inside the store itself.
MAX_MESSAGE_CHARS = 4000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConversationContextStore:
    """In-memory conversation state, bounded and thread-safe."""

    def __init__(
        self,
        max_conversations: int = MAX_CONVERSATIONS,
        max_messages: int = MAX_MESSAGES,
    ) -> None:
        self._max_conversations = max_conversations
        self._max_messages = max_messages
        self._lock = threading.Lock()
        self._conversations: dict[str, dict] = {}

    # -- reading ----------------------------------------------------------

    def get(self, conversation_id: str | None) -> dict | None:
        """The conversation's state, or None if it is unknown."""
        if not conversation_id:
            return None
        with self._lock:
            state = self._conversations.get(conversation_id)
            return dict(state) if state is not None else None

    def known_facts(self, conversation_id: str | None) -> dict:
        """Facts established earlier in this conversation ({} if none)."""
        state = self.get(conversation_id)
        if not state:
            return {}
        return dict(state.get("known_facts") or {})

    # -- writing ----------------------------------------------------------

    def ensure(self, conversation_id: str | None = None) -> dict:
        """Return the conversation, creating it if needed.

        An empty/missing id is replaced by a freshly minted one, so a
        first-time caller gets a conversation id back to reuse.
        """
        with self._lock:
            if conversation_id and conversation_id in self._conversations:
                state = self._conversations[conversation_id]
                self._touch(state)
                return dict(state)

            new_id = conversation_id or f"c_{uuid.uuid4().hex[:12]}"
            state = {
                "conversation_id": new_id,
                "messages": [],
                "current_intent": None,
                "incident_category": None,
                "known_facts": {},
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._conversations[new_id] = state
            self._evict_locked()
            return dict(state)

    def record(
        self,
        conversation_id: str | None = None,
        *,
        role: str,
        content: str,
        current_intent: str | None = None,
        incident_category: str | None = None,
        known_facts: dict | None = None,
    ) -> dict:
        """Append one exchange and merge any state it carries.

        `known_facts` merges (later values win); None never overwrites
        an established value — losing a fact the user already gave
        would make the next turn contradict this one.
        """
        with self._lock:
            if conversation_id and conversation_id in self._conversations:
                state = self._conversations[conversation_id]
            else:
                new_id = conversation_id or f"c_{uuid.uuid4().hex[:12]}"
                state = {
                    "conversation_id": new_id,
                    "messages": [],
                    "current_intent": None,
                    "incident_category": None,
                    "known_facts": {},
                    "created_at": _now(),
                    "updated_at": _now(),
                }
                self._conversations[new_id] = state
                self._evict_locked()

            state["messages"].append(
                {
                    "role": role,
                    "content": (content or "")[:MAX_MESSAGE_CHARS],
                    "at": _now(),
                }
            )
            if len(state["messages"]) > self._max_messages:
                del state["messages"][: -self._max_messages]

            if current_intent:
                state["current_intent"] = current_intent
            if incident_category:
                state["incident_category"] = incident_category
            if known_facts:
                merged = dict(state["known_facts"])
                for key, value in known_facts.items():
                    if value is None or value == "":
                        continue
                    merged[str(key)[:120]] = str(value)[:500]
                # Bounded: oldest facts drop out rather than the dict
                # growing without limit.
                while len(merged) > MAX_FACTS:
                    merged.pop(next(iter(merged)))
                state["known_facts"] = merged

            state["updated_at"] = _now()
            return dict(state)

    # -- internals --------------------------------------------------------

    def _touch(self, state: dict) -> None:
        """Mark as recently used, and move it to the insertion end."""
        state["updated_at"] = _now()
        self._conversations[state["conversation_id"]] = state

    def _evict_locked(self) -> None:
        """Drop least-recently-updated conversations beyond the cap."""
        while len(self._conversations) > self._max_conversations:
            oldest = min(
                self._conversations.items(),
                key=lambda item: item[1]["updated_at"],
            )
            del self._conversations[oldest[0]]

    # -- introspection (tests, health) ------------------------------------

    def size(self) -> int:
        with self._lock:
            return len(self._conversations)


# One store per process, the way the service holds its other state.
CONVERSATIONS = ConversationContextStore()
