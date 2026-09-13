from __future__ import annotations

import threading
import time
from collections import OrderedDict


class ConversationStore:
    def __init__(
        self,
        max_conversations: int = 500,
        max_messages: int = 8,
        ttl_seconds: int = 1800,
    ) -> None:
        self._max_conversations = max_conversations
        self._max_messages = max_messages
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._store: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()

    def _purge_expired(self, now: float) -> None:
        expired = [
            key for key, (touched, _) in self._store.items() if now - touched > self._ttl
        ]
        for key in expired:
            del self._store[key]

    def get(self, conversation_id: str | None, now: float | None = None) -> list[dict]:
        if not conversation_id:
            return []

        timestamp = now if now is not None else time.time()
        with self._lock:
            self._purge_expired(timestamp)
            entry = self._store.get(conversation_id)
            if entry is None:
                return []
            self._store.move_to_end(conversation_id)
            return [dict(message) for message in entry[1]]

    def append(
        self,
        conversation_id: str | None,
        user_message: str,
        assistant_answer: str,
        now: float | None = None,
    ) -> None:
        if not conversation_id:
            return

        timestamp = now if now is not None else time.time()
        with self._lock:
            self._purge_expired(timestamp)
            _, messages = self._store.get(conversation_id, (timestamp, []))
            messages = list(messages)
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": assistant_answer})
            messages = messages[-self._max_messages :]

            self._store[conversation_id] = (timestamp, messages)
            self._store.move_to_end(conversation_id)

            while len(self._store) > self._max_conversations:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)
