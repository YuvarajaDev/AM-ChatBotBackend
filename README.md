# AllMasters AI Chatbot — Backend

An AI-powered chatbot for the AllMasters shipping platform. Built with FastAPI, LiteLLM, AWS Bedrock (Claude Haiku), MCP (Model Context Protocol). The React frontend lives in a **separate repo**.

---

## Repos

| Repo | Path | GitHub |
|---|---|---|
| Backend (this repo) | `C:\Users\yuvaraja.g\Documents\am-chatbot` | TBD |
| Frontend | `C:\Users\yuvaraja.g\Documents\AM\AM-ChatBotUI` | `YuvarajaGovindharajan/AM-ChatBotUI` |

The two are deployed independently — frontend served statically (e.g. nginx), backend behind a separate API origin. CORS in `api.py` must be tightened from `["*"]` before going live.

---

## Architecture Overview

```
Frontend (React + Vite, separate repo)
    └── POST /chat  (SSE stream)
          └── FastAPI (chatbot/api.py)
                └── chat_engine.py  — agentic loop
                      ├── LiteLLM → AWS Bedrock (Claude Haiku)
                      └── MCP Client → mcp_server/server.py (subprocess, stdio)
                                          ├── authenticate        → AM /user/getUserRoles + /user/login
                                          ├── search_schedule     → AM /schedules/search
                                          ├── get_booking_status  → AM /bookings/{id}/status
                                          ├── get_milestones      → AM /milestone/getRefineMilestoneByAMBookingId
                                          └── update_milestone    → AM /milestone/milestoneRefine
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | AWS Bedrock — `claude-haiku-4-5-20251001` via LiteLLM |
| Backend API | FastAPI + Uvicorn |
| MCP Server | `mcp` library (stdio transport, spawned as subprocess per chat request) |
| Database | PostgreSQL (psycopg2 connection pool) |
| Frontend | React 18 + Vite (SSE streaming) — separate repo |
| Auth (app) | bcrypt + PyJWT (HS256) |
| Auth (AM) | AES-encrypted login (CryptoJS-compatible) → AllMasters JWT (RS256) |

---

## Project Structure

```
am-chatbot/
├── chatbot/
│   ├── api.py            — FastAPI endpoints (chat, auth, AM passthrough)
│   ├── auth.py           — App JWT (bcrypt + PyJWT)
│   ├── chat_engine.py    — Agentic loop (LiteLLM + MCP + SSE)
│   ├── db.py             — PostgreSQL (users, chats, messages, sessions)
│   │                       Includes _sanitize_tool_pairs to repair orphan tool_use
│   ├── models.py         — Pydantic request/response models
│   └── session.py        — AM JWT storage wrapper
│
├── mcp_server/
│   ├── server.py         — FastMCP server, exposes 5 tools
│   └── tools/
│       ├── auth.py             — authenticate_user (AES encrypt + AM login)
│       ├── booking.py          — get_booking_status_data
│       ├── milestones.py       — get_milestones + update_milestone
│       ├── milestone_config.py — config for ~30 milestone types
│       ├── schedule.py         — search_schedule_data (mock fallback)
│       └── utils.py            — decode_am_jwt, get_role_name, _auth_headers
│
├── .env                  — Environment variables (gitignored)
├── .env.example          — Template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Environment Variables (.env)

```env
# LLM — AWS Bedrock
LLM_MODEL=bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION_NAME=ap-south-1

# AllMasters API
AM_API_BASE_URL=http://localhost:3000

# AllMasters AES encryption key (matches AM frontend CryptoJS key)
AM_ENCRYPTION_KEY=your_am_encryption_key

# MCP Server
MCP_SERVER_SCRIPT=mcp_server/server.py

# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=am_chatbot
DB_USER=postgres
DB_PASSWORD=your_password

# App JWT
JWT_SECRET_KEY=change-this-to-a-long-random-secret
JWT_EXPIRE_DAYS=7
```

---

## Database Tables

| Table | Purpose |
|---|---|
| `users` | App users (email + bcrypt password hash) |
| `chats` | Chat sessions owned by a user |
| `messages` | All messages per chat. Roles: `user`, `assistant`, `tool`, `assistant_tool_call`. The `tool_name` column stores the tool_call_id for `tool` rows. |
| `sessions` | AllMasters JWT stored per `(user_id, chat_id)` |

---

## Two-JWT System

### 1. App JWT
- Issued by FastAPI on register/login
- Signs with `JWT_SECRET_KEY` (HS256)
- Protects all `/chat/*` endpoints via `Authorization: Bearer <token>`
- Stored in browser `localStorage`

### 2. AllMasters (AM) JWT
- Obtained via the secure auth modal → `POST /chat/am-auth` (or, legacy path, via the `authenticate` MCP tool)
- Stored in `sessions` table keyed by `(user_id, chat_id)`
- Automatically injected into MCP tool calls that require it
- Never exposed in the SSE stream to the frontend

---

## MCP Tools (5 total)

| Tool | Auth Required | Description |
|---|---|---|
| `authenticate` | No | Calls `getUserRoles` for dynamic type, AES-encrypts password, calls AM `/user/login`. Handles "already logged in" by auto-logout + retry. |
| `search_schedule` | No | Port-to-port vessel schedule search. Mock fallback if AM API unreachable. |
| `get_booking_status` | AM JWT | Fetches booking status from AM API. |
| `get_milestones` | AM JWT | Fetches next pending milestone (status=0), checks role access, returns `isAccess` + `requiredFields`. |
| `update_milestone` | AM JWT | Role check → portal check → field validation → POST to AM. Auto-rewrites `fileLabel` on uploads to match required field name. |

**Auth-required tools** are defined in `chat_engine.py`:

```python
AUTH_REQUIRED_TOOLS = {"get_booking_status", "get_milestones", "update_milestone"}
```

If no AM JWT in session → engine returns a stub `{"error": "not_authenticated"}` to the LLM, sets `auth_pending = True`, lets the LLM produce a reassuring message, and emits an `auth_required` SSE event after the LLM finishes streaming. The frontend opens the modal; on success it auto-resends the user's original message.

---

## Secure AM Auth Flow (modal-based)

```
1. User asks a question that needs AM auth ("what's my booking status...")
2. LLM calls get_booking_status / get_milestones / update_milestone
3. chat_engine sees no AM JWT → injects {"error":"not_authenticated"} as tool result
4. LLM streams a reassuring message ("I need to authenticate your AM credentials,
   please use the secure popup...")
5. After "stop" finish_reason, chat_engine emits SSE event: auth_required
6. Frontend waits ~1.5s (so user can read the message), then opens modal
7. User enters email + password in modal (NOT in chat — never enters chat stream
   or DB messages or LLM context)
8. Modal POSTs to /chat/am-auth
   → backend calls authenticate_user(email, password)
   → on success: stores AM JWT in sessions table
   → calls db.delete_trailing_turn(chat_id) to remove the poisoned
     tool_call/tool_result/assistant triplet from messages
9. Frontend slices the corresponding 2 messages from local React state and
   auto-resends the original user message
10. Second pass through chat_engine — AM JWT now present, tool runs cleanly
```

The `delete_trailing_turn` cleanup is essential: without it the LLM keeps replaying the "please authenticate" message because its history still shows the failed turn.

---

## AllMasters Login Internal Flow (used by `authenticate` tool and `/chat/am-auth`)

```
1. get_user_type(email, encrypted_password)
       → POST /user/getUserRoles
       → returns role → maps to type (1→1, 6/7→2, 2-5→3)

2. proceed_login(email, encrypted_password, user_type)
       → POST /user/login
       → returns loginData (data field is JSON string)

3. json.loads(loginData["data"]) → inner
4. decode_am_jwt(inner["token"]) → { userId, role, type, status }

5. If "User Already Logged In":
       → proceed_logout(userId, type, token)
       → retry proceed_login

6. Return { success, jwt, user_id, username, role, type }
```

---

## Milestone System

### get_milestones
- Calls `POST /milestone/getRefineMilestoneByAMBookingId`
- Finds **first pending milestone** (`milestoneStatus == 0`)
- Decodes AM JWT to get user role
- Checks `milestoneActionRole` vs user role → sets `isAccess`
- Returns enriched milestone:
  - `isAccess: true` → includes `requiredFields` from local config
  - `isAccess: false` → includes `actionRoleNames`, empty `requiredFields`

### update_milestone
- Re-fetches milestone via `get_milestones` (single source of truth)
- Role check → portal check (`shouldPerformOnAm`) → text/date field validation → file validation
- For uploads: rewrites `fileLabel` of each uploaded file to match the first required file field's `name`, so frontend filename mismatches don't fail validation
- POSTs full milestone object + collected data + file uploads to `/milestone/milestoneRefine`

### Role System (utils.py)

| Role ID | Name |
|---|---|
| 1 | User |
| 2 | Admin |
| 3 | OBT |
| 4 | RDT |
| 5 | OT |
| 6 | Origin CFS |
| 7 | Destination CFS |

### Milestone Config (milestone_config.py)
~30 milestone types, each with:
- `requiredFields` — list of `{ type, label, name }` where type is `text / date / dateAndTime / file / checkbox / switch`
- `isFileUpload` — whether file upload is needed
- `proceedMileStone` — whether user needs to proceed on portal
- `AMSDetails` is special — has role-based sub-configs (OT=role 5, FF=others)

---

## LLM System Prompt Behaviour

| Scenario | LLM behaviour |
|---|---|
| Schedule search | Calls `search_schedule` directly, no login needed |
| Booking / milestones, no AM session | Calls the tool first; on `not_authenticated` error, tells the user the secure popup will appear and to enter credentials there. **Never** asks for AM email or password in chat. |
| `isAccess: false` on milestone | Tells user who can update it, does NOT collect fields |
| `isAccess: true`, no required fields | Asks confirmation, calls `update_milestone` |
| `isAccess: true`, has required fields | Collects each field conversationally (text/date via chat, file via upload button using `fileLabel`), confirms, calls `update_milestone` |
| `portal_required: true` | Tells user to complete on AllMasters portal |
| File attachment present | Sees `[File attached: <filename>]` marker injected into history (never the bytes — only the filename, ~10 tokens) |

---

## API Endpoints

### Public
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Login, returns app JWT |
| GET | `/health` | Health check |

### Protected (requires app JWT — `Authorization: Bearer <app jwt>`)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/chat/new` | Create new chat session |
| POST | `/chat` | Send message — SSE stream response |
| POST | `/chat/am-auth` | Secure AM credentials submit (from frontend modal) |
| GET | `/chat/list` | List all chats for user |
| GET | `/chat/{chat_id}/history` | Load chat history |
| DELETE | `/chat/{chat_id}` | Clear chat + AM session |

### Test / Direct passthroughs (Postman testing — auth via AM JWT or none)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/milestones` | Direct `get_milestones` (body: `{"data":[{"bookingId":"..."}]}`, header: AM JWT) |
| POST | `/milestones/update` | Direct `update_milestone` (body: `{bookingId, milestoneName, collectedData, fileUploads}`, header: AM JWT) |
| POST | `/user/loginCheck` | Direct AM login (body: `{username, password}`) — returns AM JWT |
| POST | `/schedule/search` | Direct schedule search (body: `{pol, pod}`) |

These bypass LLM/MCP — useful for verifying AM API integration without spending tokens.

---

## SSE Event Types

| Event type | When |
|---|---|
| `token` | LLM is streaming a text chunk |
| `tool_call` | A tool is being called (JWT and file_uploads stripped from payload) |
| `tool_result` | Tool returned a result |
| `auth_required` | Tool blocked by missing AM JWT — frontend should open the secure modal. Carries `pending_message` (the user's original message) for auto-resend. Emitted **after** the LLM finishes its reassuring message and **before** `done`. |
| `done` | Response complete |
| `error` | Something went wrong |

---

## Known Issues / Notes

- **MCP subprocess + VS Code debugpy**: Never use `print()` inside MCP server tools. Both `stdout` (breaks JSON-RPC) and `stderr` (hijacked by debugpy) are unusable. Use a log file if debugging is needed.
- **AM JWT expiry**: JWT has ~1 hour window (`exp` field). Currently only `None` is checked, not validity. Expired JWTs reach AM API and produce 401s. Auto re-auth on 401 not yet implemented.
- **Orphan tool_use after dropped streams**: If the SSE connection drops between saving `assistant_tool_call` and saving the matching `tool` row, history would have a tool_use with no tool_result and Bedrock rejects it. `db._sanitize_tool_pairs` (called from `load_history`) injects a stub `{"error":"tool_call_interrupted"}` for any unfulfilled tool_use IDs, so retries replay cleanly.
- **File upload size**: Files are passed as base64 in JSON body. No explicit size limit set yet — set proxy/Uvicorn limits before live.
- **CORS**: `api.py:57` is `allow_origins=["*"]` — must be tightened to the frontend origin before live.
- **Per-request MCP subprocess spawn**: `chat_engine.py` spawns `mcp_server/server.py` as a child process per chat request. Adds 200–500ms latency per turn. Long-term: collapse MCP into in-process imports or run as a long-lived sidecar.

---

## Running the Project

### Backend
```bash
cd C:\Users\yuvaraja.g\Documents\am-chatbot
.\venv\Scripts\activate
pip install -r requirements.txt
uvicorn chatbot.api:app --reload --port 8000
```

### Frontend (separate repo)
```bash
cd C:\Users\yuvaraja.g\Documents\AM\AM-ChatBotUI
npm install
npm run dev
```
