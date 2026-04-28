"""
chatbot/models.py
==================
Pydantic request/response models.
"""

from pydantic import BaseModel
from typing import Optional


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name:     str
    email:    str
    password: str


class LoginRequest(BaseModel):
    email:    str
    password: str


class AuthResponse(BaseModel):
    success: bool
    token:   str
    user:    dict


# ── Chat ──────────────────────────────────────────────────────────────────────

class FileAttachment(BaseModel):
    fileName:  str
    filePath:  str   # data:<mime>;base64,<data>
    fileLabel: str


class ChatRequest(BaseModel):
    chat_id:  str
    message:  str
    am_jwt:   Optional[str]            = None   # AM JWT from frontend if user came from AM portal
    file:     Optional[FileAttachment] = None   # file attached by user in chat


class AMAuthRequest(BaseModel):
    chat_id:  str
    email:    str
    password: str


class NewChatResponse(BaseModel):
    success: bool
    chat_id: str


class HistoryMessage(BaseModel):
    role:      str
    content:   str
    timestamp: str


class HistoryResponse(BaseModel):
    success:  bool
    chat_id:  str
    messages: list[HistoryMessage]


class BaseResponse(BaseModel):
    success: bool
    message: Optional[str] = None
