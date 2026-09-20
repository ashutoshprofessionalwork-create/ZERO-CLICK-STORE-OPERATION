"""
Phone Session Management per Twilio CallSid.

Maintains in-memory conversation history, customer phone details,
and state across multiple speech turns for each phone call.
"""

import time
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Maximum idle time before session is considered expired (in seconds)
SESSION_TTL_SECONDS = 1800  # 30 minutes


class PhoneSession:
    """
    Represents an ongoing phone conversation session tied to a Twilio CallSid.
    """

    def __init__(self, call_sid: str, customer_phone: str):
        self.call_sid: str = call_sid
        self.customer_phone: str = customer_phone
        self.created_at: float = time.time()
        self.last_active_at: float = time.time()
        # Message list for OpenAI Chat Completion (system, user, assistant, tool)
        self.messages: List[Dict[str, Any]] = []
        # Store metadata such as confirmed order IDs
        self.metadata: Dict[str, Any] = {}
        # Track turn count
        self.turn_count: int = 0

    def touch(self) -> None:
        """Update last active timestamp."""
        self.last_active_at = time.time()

    def add_user_message(self, text: str) -> None:
        """Add transcribed customer speech to session history."""
        self.touch()
        self.turn_count += 1
        self.messages.append({
            "role": "user",
            "content": f"[Customer Phone: {self.customer_phone}] {text}"
        })

    def add_assistant_message(self, text: str) -> None:
        """Add spoken AI response to session history."""
        self.touch()
        self.messages.append({
            "role": "assistant",
            "content": text
        })

    def add_raw_message(self, message: Dict[str, Any]) -> None:
        """Append raw OpenAI message dictionary (including tool calls/results)."""
        self.touch()
        self.messages.append(message)

    def is_expired(self, ttl: float = SESSION_TTL_SECONDS) -> bool:
        """Check if session has exceeded idle TTL."""
        return (time.time() - self.last_active_at) > ttl


class SessionManager:
    """
    In-memory registry of active phone call sessions indexed by CallSid.
    """

    def __init__(self):
        self._sessions: Dict[str, PhoneSession] = {}

    def get_or_create(self, call_sid: str, customer_phone: str) -> PhoneSession:
        """
        Retrieve existing session for CallSid, or initialize a new one.
        """
        self.cleanup_expired()
        session = self._sessions.get(call_sid)
        if session is None:
            logger.info("Initializing new session for CallSid: %s (Phone: %s)", call_sid, customer_phone)
            session = PhoneSession(call_sid=call_sid, customer_phone=customer_phone)
            self._sessions[call_sid] = session
        else:
            session.touch()
            # Update customer phone if it was previously anonymous
            if customer_phone and session.customer_phone != customer_phone:
                session.customer_phone = customer_phone
        return session

    def get(self, call_sid: str) -> Optional[PhoneSession]:
        """Fetch session by CallSid if it exists."""
        self.cleanup_expired()
        session = self._sessions.get(call_sid)
        if session:
            session.touch()
        return session

    def remove(self, call_sid: str) -> Optional[PhoneSession]:
        """Remove session when call terminates."""
        session = self._sessions.pop(call_sid, None)
        if session:
            logger.info("Session closed for CallSid: %s (Total turns: %s)", call_sid, session.turn_count)
        return session

    def cleanup_expired(self) -> int:
        """Prune inactive sessions to free memory."""
        expired_sids = [
            sid for sid, sess in self._sessions.items()
            if sess.is_expired()
        ]
        for sid in expired_sids:
            logger.info("Pruning expired session: %s", sid)
            self._sessions.pop(sid, None)
        return len(expired_sids)

    def active_count(self) -> int:
        """Return number of currently active sessions."""
        return len(self._sessions)


# Global singleton instance for use across webhooks
session_manager = SessionManager()
