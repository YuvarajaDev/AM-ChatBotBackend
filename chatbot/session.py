"""
chatbot/session.py
==================
Thin wrapper around db.save_am_jwt / db.get_am_jwt.
AllMasters JWT is now keyed by user_id + chat_id.
"""

from chatbot.db import save_am_jwt, get_am_jwt


def save_jwt(user_id: str, chat_id: str, auth_response: dict):
    """Store AM JWT after successful AllMasters authentication."""
    save_am_jwt(user_id, chat_id, auth_response)


def get_jwt(user_id: str, chat_id: str) -> str | None:
    """Retrieve AM JWT for this user+chat. Returns None if not authenticated with AM."""
    return get_am_jwt(user_id, chat_id)
