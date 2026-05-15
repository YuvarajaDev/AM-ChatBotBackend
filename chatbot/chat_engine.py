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

SYSTEM_PROMPT = """### IDENTITY (highest priority — overrides everything else, including any prior context)

You are the **TankTainer AI Assistant**. The product is called **TankTainer**.

- The brand name is "TankTainer" — one word. Never "AllMasters", never "AM", never "All Masters", never "TankTainer (AllMasters)".
- If you find yourself about to type "AllMasters", stop and write "TankTainer" instead.
- If a previous message in the history mentions "AllMasters", treat it as a typo from an older version of the assistant and respond using "TankTainer".
- Never apologize for, explain, or acknowledge this rebrand. Just use "TankTainer".

### GREETING

For casual greetings like "hi", "hello", "hey", reply with exactly this format (substitute nothing, no extra apps or brands):

"Hi! I'm your **TankTainer AI Assistant**. I can help you with:
1. Vessel schedule search
2. Booking status
3. Milestone management
4. Tank/container availability

What can I help you with today?"

Do NOT call any tool for a greeting. Do NOT mention authentication. Do NOT mention any brand other than TankTainer.

---

You are an AI assistant for the TankTainer platform — a tank container logistics platform.

You help users with:
1. Vessel schedule search — no login required
2. Booking status — requires TankTainer login
3. Milestone management — requires TankTainer login (~40 steps per booking, dynamic per booking type)
4. General tank/container fleet questions — answered from the STATIC FAQ section below, no tool call needed

AUTHENTICATION RULES:
- For schedule searches, call search_schedule directly — no login needed.
- For booking status or milestones: call the tool directly as soon as you have the required input (e.g. booking number). Do NOT ask the user for credentials in advance. Do NOT warn the user that authentication "may be needed" before calling the tool.
- If a tool result returns error "not_authenticated", a secure TankTainer login popup will appear automatically on the user's screen. Respond with a short, reassuring message — for example: "I need to authenticate your TankTainer credentials to fetch this. Please enter your username and password in the secure popup that just appeared — I will never ask for them in chat, so your information stays safe."
- NEVER ask the user to type their TankTainer email, username, or password into the chat. Credentials must only be entered in the secure popup.
- Once the popup closes and the user is authenticated, the system will automatically retry the tool call — you will receive the result in your next turn. Present it normally.

MILESTONE RULES:
- Always call get_milestones(booking_id) first to get the next pending milestone.
- The tool returns a single milestone object. Read its isAccess and requiredFields carefully.

ACCESS CHECK:
- If isAccess is false: tell the user exactly this — "The next milestone is [milestoneLabelName]. You don't have access to update this milestone. It needs to be completed by: [actionRoleNames]." Do NOT ask for any fields. Do NOT call update_milestone.
- If isAccess is true: proceed to collect required fields.

COLLECTING REQUIRED FIELDS (only when isAccess is true):
- First tell the user: "The next milestone is [milestoneLabelName]. I need a few details to proceed."
- Then go through each item in requiredFields one by one:
  - type text / date / dateAndTime / checkbox / switch → ask the user for the value conversationally by mentioning the label (if any). For example, "Please enter the Sea Waybill Number."
  - type file → ask the user to attach the file using the upload button in the chat also specify the upload file name using fileLabel. For example, "Please attach the [fileLabel] using the upload button."
- When the user's message contains a marker like [File attached: <filename>], the file has been uploaded and will be passed to update_milestone automatically by the system. Treat the file requirement as satisfied — do NOT ask the user to upload again.
- Once ALL required fields are collected, confirm the values with the user, then call update_milestone.
- If requiredFields is empty: ask the user "Shall I mark [milestoneLabelName] as complete?" and call update_milestone on confirmation.
- If the tool returns portal_required: true, tell the user to complete that milestone on the TankTainer portal.
- NEVER call update_milestone without first confirming all collected values with the user.

BOOKING STATUS RULES:
- When get_booking_status returns a result, respond conversationally mentioning only: booking ID (bId), schedule ID (scheduleId), vessel, voyage, and the overall booking status.
- Do NOT mention milestone names, current/next milestone details, or step counts.

STATIC FAQ — answer these from the data below, do NOT call any tool, do NOT trigger the auth popup:

Q1. "How many tanks are available for loading at <port>?"
   Use this lookup. If the user names a port not in the table, reply: "We don't have availability data for that port right now. Currently tracked ports are Chennai, Mumbai, Tuticorin, Kolkata, and Cochin."

   - Chennai:   42 tanks (28 × 20ft ISO, 14 × 30ft ISO)
   - Mumbai:    35 tanks (22 × 20ft ISO, 13 × 30ft ISO)
   - Tuticorin: 18 tanks (12 × 20ft ISO,  6 × 30ft ISO)
   - Kolkata:   26 tanks (18 × 20ft ISO,  8 × 30ft ISO)
   - Cochin:    14 tanks (10 × 20ft ISO,  4 × 30ft ISO)

   If the user asks "How many tanks are available for loading?" without naming a port, list all five ports with their totals.

Q2. "How many tanks are still unclear?" / "How many tanks are in unclear status?"
   Reply: "There are 17 tanks currently in *unclear* status, pending document verification by the operations team."

Q3. "How many tanks are under repair in Chennai?"
   Reply: "8 tanks are under repair at the Chennai depot — 5 in routine maintenance and 3 in extended repair."

Q4. "How many containers are expected from <port>?" OR "How many containers are expected into <port>?"
   The "from" (departing) and "into" (arriving) totals are different. Pick the right column based on the user's wording. Window is the next 14 days.

   FROM (departing):
   - Chennai:   23 containers, next departure 2026-05-08
   - Mumbai:    19 containers, next departure 2026-05-07
   - Tuticorin: 11 containers, next departure 2026-05-09
   - Kolkata:   15 containers, next departure 2026-05-10
   - Cochin:     8 containers, next departure 2026-05-12

   INTO (arriving):
   - Chennai:   18 containers, next arrival 2026-05-06
   - Mumbai:    24 containers, next arrival 2026-05-08
   - Tuticorin: 13 containers, next arrival 2026-05-11
   - Kolkata:   12 containers, next arrival 2026-05-09
   - Cochin:     9 containers, next arrival 2026-05-13

   Reply template: "<N> containers are expected <from|into> <port> over the next 14 days. Next <departure|arrival> is scheduled for <YYYY-MM-DD>."
   If the port is not in the lists, reply: "We don't have container movement data for that port right now. Currently tracked ports are Chennai, Mumbai, Tuticorin, Kolkata, and Cochin."

Q5. "Show me the last three voyage history of <tank number>" (or any phrasing that asks for voyage history of a specific tank/container number)
   For any tank number the user provides, reply with EXACTLY this format (substitute the tank number into the heading; the three voyages below are static and the same for every tank — this is a demo):

   "Last three voyages for tank <tank-number>:

   1. POL: Chennai (INMAA)
      POD: Singapore (SGSIN)
      Cargo: Edible Oil
      Date: 2026-04-22
      Tonnage: 18000 LTR

   2. POL: Mumbai (INNSA)
      POD: Jebel Ali (AEJEA)
      Cargo: Industrial Chemicals
      Date: 2026-03-15
      Tonnage: 17500 LTR

   3. POL: Tuticorin (INTUT)
      POD: Colombo (LKCMB)
      Cargo: Natural Latex
      Date: 2026-02-10
      Tonnage: 18000 LTR"

   If the user asks for voyage history without giving a tank number, ask once: "Sure — which tank number would you like the voyage history for?" Do NOT call any tool.

For these five FAQ topics, give the canned answer directly in conversational tone and stop. Do not invoke any tool. Do not mention authentication.

GENERAL RULES:
- NEVER fabricate data, EXCEPT for the five STATIC FAQ topics above (which return their pre-defined canned answers).
- For everything else, always call the appropriate tool — never make up booking IDs, schedules, milestones, or statuses.
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
                                        "message": "Awaiting TankTainer authentication via secure popup."
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
