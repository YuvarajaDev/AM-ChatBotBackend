"""
chatbot/chat_engine.py
=======================
Agentic loop — LiteLLM + MCP client + SSE streaming.

Changes from Phase 1:
  - user_id now passed in (from our JWT)
  - AM JWT session keyed by user_id + chat_id
  - Chat title set from first user message
"""

import os
import sys
import json
import litellm
from dotenv import load_dotenv
from fastapi import Request
from typing import AsyncGenerator

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from chatbot import db
from chatbot import session as sess

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0")

MCP_SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    os.getenv("MCP_SERVER_SCRIPT", "mcp_server/server.py")
)

AUTH_REQUIRED_TOOLS = {"get_booking_status", "get_milestones", "update_milestone"}

SYSTEM_PROMPT = """You are an AI assistant for the AllMasters shipping platform.

You help users with:
1. Vessel schedule search — no login required
2. Booking status — requires AllMasters login
3. Milestone management — requires AllMasters login (~40 steps per booking, dynamic per booking type)

AUTHENTICATION RULES:
- For schedule searches, call search_schedule directly — no login needed.
- For booking status or milestones: call the tool directly as soon as you have the required input (e.g. booking number). Do NOT ask the user for credentials in advance. Do NOT warn the user that authentication "may be needed" before calling the tool.
- If a tool result returns error "not_authenticated", a secure AllMasters login popup will appear automatically on the user's screen. Respond with a short, reassuring message — for example: "I need to authenticate your AllMasters credentials to fetch this. Please enter your username and password in the secure popup that just appeared — I will never ask for them in chat, so your information stays safe."
- NEVER ask the user to type their AllMasters email, username, or password into the chat. Credentials must only be entered in the secure popup.
- Once the popup closes and the user is authenticated, the system will automatically retry the tool call — you will receive the result in your next turn. Present it normally.

MILESTONE RULES:
- Always call get_milestones(booking_id) first to get the next pending milestone.
- The tool returns a single milestone object. Read its milestoneName, isAccess and requiredFields carefully.

ON-HOLD CHECK:
- If isOnHold is true: tell the user — "The [milestoneLabelName] milestone is currently on hold. Would you like me to unhold it and proceed?"
  - If user says No: acknowledge and stop.
  - If user says Yes: collect all requiredFields exactly as you would for a normal milestone (text, date, file — same rules apply), then call update_milestone once everything is provided.

ACCESS CHECK:
- If isAccess is false: tell the user exactly this — "The next milestone is [milestoneLabelName]. You don't have access to update this milestone. It needs to be completed by: [actionRoleNames]." Do NOT ask for any fields. Do NOT call update_milestone.
- If isAccess is true: proceed below.

COLLECTING REQUIRED FIELDS (only when isAccess is true):
- If the milestone has shouldPerformAM: true, tell the user: "The [milestoneLabelName] milestone needs to be completed on the AllMasters portal. Please proceed there." Do NOT call update_milestone.
- If the milestone has an instruction field, follow it exactly before doing anything else with requiredFields.
- First tell the user: "The next milestone is [milestoneLabelName]. I need a few details to proceed."
- Then go through each item in requiredFields one by one:
  - type text / date / dateAndTime / checkbox / switch → ask the user for the value conversationally by mentioning the label (if any). For example, "Please enter the Sea Waybill Number."
  - type file → ask the user to attach the file using the upload button in the chat also specify the upload file name using fileLabel. For example, "Please attach the [fileLabel] using the upload button."
- When the user's message contains a marker like [File attached: <filename>], the file has been uploaded and will be passed to update_milestone automatically by the system. Treat the file requirement as satisfied — do NOT ask the user to upload again.
- Once ALL required fields are collected, confirm the values with the user, then call update_milestone.
- If requiredFields is empty: ask the user "Shall I mark [milestoneLabelName] as complete?" and call update_milestone on confirmation.
- If the tool returns portal_required: true, tell the user to complete that milestone on the AllMasters portal.
- NEVER call update_milestone without first confirming all collected values with the user.

BOOKING STATUS RULES:
- When get_booking_status returns a result, respond conversationally mentioning only: booking ID (bId), schedule ID (scheduleId), vessel, voyage, and the overall booking status.
- Do NOT mention milestone names, current/next milestone details, or step counts.

GENERAL RULES:
- NEVER fabricate data. Always call tools.
- NEVER add disclaimers or caveats.
- Present data in clean card format, no markdown tables.
- NEVER read or open any uploaded files. They are only for the user's reference and will be processed by the MCP tools. You can treat file uploads as a simple confirmation that the user has provided the required document, without needing to know its contents.
"""


def _mcp_tool_to_openai(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name":        tool.name,
            "description": tool.description or "",
            "parameters":  tool.inputSchema
        }
    }


async def stream_response(
    chat_id:         str,
    user_id:         str,
    user_message:    str,
    frontend_jwt:    str | None,
    http_request:    Request,
    file_attachment: dict | None = None   # { fileName, filePath (base64), fileLabel }
) -> AsyncGenerator[str, None]:
    """
    Async generator — drives the agentic loop and yields SSE events.
    user_id is from our app JWT (not AllMasters).
    """

    # Save user message + set chat title from first message
    db.save_message(chat_id, "user", user_message)
    db.set_chat_title(chat_id, user_message[:50])

    # Resolve AM JWT: frontend → DB session → None
    am_jwt = frontend_jwt or sess.get_jwt(user_id, chat_id)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[MCP_SERVER_SCRIPT]
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as mcp:
                await mcp.initialize()

                tools_result = await mcp.list_tools()
                tools = [_mcp_tool_to_openai(t) for t in tools_result.tools]

                history = db.load_history(chat_id, limit=20)

                # In-memory marker so the LLM knows a file is attached this turn.
                # File bytes never go to the LLM — only the filename.
                if file_attachment and history and history[-1].get("role") == "user":
                    history[-1]["content"] += f"\n\n[File attached: {file_attachment.get('fileName')}]"

                accumulated_text = ""
                auth_pending    = False   # set when a tool is blocked by missing AM JWT

                while True:
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
                    chunks = []

                    try:
                        response = await litellm.acompletion(
                            model=MODEL,
                            messages=messages,
                            tools=tools,
                            stream=True
                        )

                        async for chunk in response:
                            if await http_request.is_disconnected():
                                return
                            chunks.append(chunk)
                            delta = chunk.choices[0].delta
                            if delta.content:
                                accumulated_text += delta.content
                                yield f"data: {json.dumps({'type': 'token', 'content': delta.content})}\n\n"

                    except Exception as e:
                        print(f"  [LLM Error] {e}")
                        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                        break

                    full_response = litellm.stream_chunk_builder(chunks, messages=messages)
                    finish_reason = full_response.choices[0].finish_reason
                    message       = full_response.choices[0].message

                    if finish_reason == "tool_calls":

                        assistant_msg = {"role": "assistant", "content": message.content}
                        if message.tool_calls:
                            assistant_msg["tool_calls"] = [
                                {
                                    "id":       tc.id,
                                    "type":     "function",
                                    "function": {
                                        "name":      tc.function.name,
                                        "arguments": tc.function.arguments
                                    }
                                }
                                for tc in message.tool_calls
                            ]
                        history.append(assistant_msg)
                        # Save with tool_calls so next turn can reconstruct for Bedrock
                        db.save_message(chat_id, "assistant_tool_call", json.dumps(assistant_msg))

                        for tc in (message.tool_calls or []):
                            if await http_request.is_disconnected():
                                return

                            tool_name  = tc.function.name
                            tool_input = json.loads(tc.function.arguments)

                            # ── File attachment injection for update_milestone ─
                            if tool_name == "update_milestone" and file_attachment:
                                tool_input["file_uploads"] = [file_attachment]

                            # ── AM JWT injection ──────────────────────────────
                            if tool_name in AUTH_REQUIRED_TOOLS:
                                current_jwt = am_jwt or sess.get_jwt(user_id, chat_id)
                                if not current_jwt:
                                    # Block the tool, preserve history integrity, let LLM
                                    # respond with a reassuring message in the next turn.
                                    result_dict = {
                                        "error":   "not_authenticated",
                                        "message": "Awaiting AllMasters authentication via secure popup."
                                    }
                                    safe_input = {k: v for k, v in tool_input.items() if k != "jwt"}
                                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'input': safe_input})}\n\n"
                                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result_dict})}\n\n"
                                    history.append({
                                        "role":         "tool",
                                        "tool_call_id": tc.id,
                                        "content":      json.dumps(result_dict)
                                    })
                                    db.save_message(chat_id, "tool", json.dumps(result_dict), tc.id)
                                    auth_pending = True
                                    continue
                                tool_input["jwt"] = current_jwt

                            # Never expose JWT in SSE stream
                            safe_input = {k: v for k, v in tool_input.items() if k not in ("jwt", "file_uploads")}
                            yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'input': safe_input})}\n\n"

                            try:
                                mcp_result  = await mcp.call_tool(tool_name, tool_input)
                                result_text = mcp_result.content[0].text
                                result_dict = json.loads(result_text)
                            except Exception as e:
                                result_dict = {"error": f"Tool execution failed: {str(e)}"}
                                result_text = json.dumps(result_dict)

                            # Store AM JWT after successful authenticate()
                            if tool_name == "authenticate" and result_dict.get("success"):
                                sess.save_jwt(user_id, chat_id, result_dict)
                                am_jwt = result_dict.get("jwt")

                            # Expired JWT — clear stale session and trigger re-auth popup.
                            if tool_name in AUTH_REQUIRED_TOOLS and result_dict.get("error") == "not_authenticated":
                                sess.clear_jwt(user_id, chat_id)
                                am_jwt = None
                                auth_pending = True

                            yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result_dict})}\n\n"

                            history.append({
                                "role":         "tool",
                                "tool_call_id": tc.id,
                                "content":      result_text
                            })
                            db.save_message(chat_id, "tool", result_text, tc.id)

                    elif finish_reason == "stop":
                        db.save_message(chat_id, "assistant", accumulated_text)
                        # Emit auth_required AFTER the reassuring message finishes streaming,
                        # so the modal opens only after the user has read it and isStreaming
                        # has flipped false on the frontend (so the auto-resend will work).
                        if auth_pending:
                            yield f"data: {json.dumps({'type': 'auth_required', 'pending_message': user_message})}\n\n"
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break

                    else:
                        yield f"data: {json.dumps({'type': 'error', 'content': f'Unexpected finish: {finish_reason}'})}\n\n"
                        break

    except Exception as e:
        print(f"  [MCP Error] {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Failed to connect to MCP server.'})}\n\n"
