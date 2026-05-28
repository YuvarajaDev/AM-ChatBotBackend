"""
chatbot/api.py
==============
FastAPI — all endpoints.

Public:
  POST /auth/register
  POST /auth/login
  GET  /health

Protected (requires our JWT):
  POST /chat/new
  POST /chat
  GET  /chat/list
  GET  /chat/{chat_id}/history
  DELETE /chat/{chat_id}
"""

import sys
import os
from contextlib import asynccontextmanager

from mcp_server.tools.schedule import search_schedule_data

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from chatbot import db
from chatbot.auth import (
    hash_password, verify_password,
    create_token, get_current_user
)
from chatbot.models import (
    RegisterRequest, LoginRequest, AMAuthRequest,
    ChatRequest, NewChatResponse, HistoryResponse, BaseResponse
)
from chatbot.chat_engine import stream_response
from chatbot import session as sess

from mcp_server.tools.milestones import (
    get_milestones   as fetch_milestones,
    update_milestone as run_update_milestone,
)
from mcp_server.tools.auth import authenticate_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="AllMasters Chatbot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth endpoints (public) ───────────────────────────────────────────────────

@app.post("/auth/register")
async def register(request: RegisterRequest):
    if db.get_user_by_email(request.email):
        raise HTTPException(status_code=400, detail="Email already registered.")
    user = db.create_user(
        name=request.name,
        email=request.email,
        password_hash=hash_password(request.password)
    )
    token = create_token(user["id"], user["email"])
    return {
        "success": True,
        "token":   token,
        "user":    {"id": user["id"], "name": user["name"], "email": user["email"]}
    }


@app.post("/auth/login")
async def login(request: LoginRequest):
    user = db.get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_token(user["id"], user["email"])
    return {
        "success": True,
        "token":   token,
        "user":    {"id": user["id"], "name": user["name"], "email": user["email"]}
    }


# ── Chat endpoints (protected) ────────────────────────────────────────────────

@app.get("/chat/list")
async def list_chats(current_user: dict = Depends(get_current_user)):
    """Return all chats for the logged-in user — used to populate sidebar."""
    chats = db.get_user_chats(current_user["user_id"])
    return {"success": True, "chats": chats}


@app.post("/chat/new", response_model=NewChatResponse)
async def new_chat(current_user: dict = Depends(get_current_user)):
    """Create a new chat session for the current user."""
    chat_id = db.create_chat(current_user["user_id"])
    return {"success": True, "chat_id": chat_id}


@app.post("/chat")
async def chat(
    request:      ChatRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Send a message — streams response via SSE."""
    # Verify this chat belongs to the current user
    owner = db.get_chat_owner(request.chat_id)
    if owner != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    return StreamingResponse(
        stream_response(
            chat_id      = request.chat_id,
            user_id      = current_user["user_id"],
            user_message = request.message,
            frontend_jwt = request.am_jwt,
            http_request = http_request,
            file_attachment = request.file.model_dump() if request.file else None,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        }
    )


@app.get("/chat/{chat_id}/history", response_model=HistoryResponse)
async def get_history(
    chat_id:      str,
    current_user: dict = Depends(get_current_user)
):
    """Load full conversation history — used on page load / chat switch."""
    owner = db.get_chat_owner(chat_id)
    if owner != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied.")
    messages = db.load_display_history(chat_id)
    return {"success": True, "chat_id": chat_id, "messages": messages}


@app.post("/chat/am-auth", response_model=BaseResponse)
async def am_auth(
    request:      AMAuthRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Secure AllMasters login — called from the frontend modal.
    Password never enters the chat stream, DB messages table, or LLM context.
    On success, stores AM JWT in sessions table keyed by (user_id, chat_id).
    """
    owner = db.get_chat_owner(request.chat_id)
    if owner != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    result = authenticate_user(request.email, request.password, request.user_type)
    if not result.get("success"):
        return {"success": False, "message": result.get("message", "Authentication failed.")}

    sess.save_jwt(current_user["user_id"], request.chat_id, result)

    # Strip the poisoned failed-auth turn from history so the upcoming retry
    # starts from clean state. The frontend will auto-resend the original
    # user message right after this returns.
    db.delete_trailing_turn(request.chat_id)

    return {"success": True, "message": "AllMasters authentication successful."}


@app.delete("/chat/{chat_id}", response_model=BaseResponse)
async def clear_chat(
    chat_id:      str,
    current_user: dict = Depends(get_current_user)
):
    """Clear all messages and AM session for a chat."""
    owner = db.get_chat_owner(chat_id)
    if owner != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied.")
    db.clear_chat(chat_id)
    return {"success": True, "message": "Chat cleared."}

@app.post("/milestones")
async def get_milestones(request: Request) -> dict:
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
        jwt = auth_header.split(" ")[1]
        body = await request.json()
        booking_id = body['data'][0].get('bookingId')
        if(not booking_id):
            raise HTTPException(status_code=400, detail="Missing bookingId in request body.")
        return fetch_milestones(jwt, booking_id)
    except HTTPException as e:
        raise e

@app.post("/user/loginCheck")
async def login_check(request: Request) -> dict:
    try:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password are required.")
        auth_result = authenticate_user(username, password)
        
        if not auth_result["success"]:
            raise HTTPException(status_code=401, detail=auth_result.get("message", "Authentication failed."))
        return auth_result
    except HTTPException as e:
        raise e

@app.post("/schedule/search")
async def search_schedule(request: Request) -> dict:
    try:
        data = await request.json()
        pol = data.get("pol")
        pod = data.get("pod")
        if not pol or not pod:
            raise HTTPException(status_code=400, detail="Both 'pol' and 'pod' are required.")
        return search_schedule_data(pol, pod)
    except HTTPException as e:
        raise e

@app.post("/milestones/update")
async def update_milestone(request: Request) -> dict:
    """
    Direct passthrough to update_milestone — bypasses LLM/MCP for Postman testing.

    Headers: Authorization: Bearer <AM JWT>
    Body:
      {
        "bookingId":      "AM-04-26-0012",
        "milestoneName":  "containerSealno",
        "collectedData":  { "containerNo": "ABCD1234567", "sealNo": "S98765" },
        "fileUploads":    [{ "fileName": "...", "filePath": "<base64>", "fileLabel": "..." }]
      }
    """
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
        jwt = auth_header.split(" ")[1]

        body           = await request.json()
        booking_id     = body.get("bookingId")
        milestone_name = body.get("milestoneName")
        collected_data = body.get("collectedData") or {}
        file_uploads   = body.get("fileUploads")  or []

        if not booking_id or not milestone_name:
            raise HTTPException(status_code=400, detail="bookingId and milestoneName are required.")

        return run_update_milestone(jwt, booking_id, milestone_name, collected_data, file_uploads)
    except HTTPException as e:
        raise e

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"success": True, "service": "am-chatbot", "status": "ok"}
