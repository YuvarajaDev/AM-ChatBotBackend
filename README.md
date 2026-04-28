# AllMasters AI Chatbot

An AI-powered chatbot for the AllMasters shipping platform. Built with FastAPI, LiteLLM, AWS Bedrock (Claude Haiku), MCP (Model Context Protocol), and a React frontend.

---

## Architecture Overview

```
Frontend (React + Vite)
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
| MCP Server | `mcp` library (stdio transport, spawned as subprocess) |
| Database | PostgreSQL (psycopg2 connection pool) |
| Frontend | React 18 + Vite (SSE streaming) |
| Auth (app) | bcrypt + PyJWT (HS256) |
| Auth (AM) | AES-encrypted login → AllMasters JWT (RS256) |

---

## Project Structure

```
am-chatbot/
├── chatbot/
│   ├── api.py            — FastAPI endpoints
│   ├── auth.py           — App JWT (bcrypt + PyJWT)
│   ├── chat_engine.py    — Agentic loop (LiteLLM + MCP + SSE)
│   ├── db.py             — PostgreSQL (users, chats, messages, sessions)
│   ├── models.py         — Pydantic request/response models
│   └── session.py        — AM JWT storage wrapper
│
├── mcp_server/
│   ├── server.py         — FastMCP server, exposes 5 tools
│   └── tools/
│       ├── auth.py           — authenticate_user (AES encrypt + AM login)
│       ├── booking.py        — get_booking_status_data
│       ├── milestones.py     — get_milestones + update_milestone
│       ├── milestone_config.py — config for ~30 milestone types
│       ├── schedule.py       — search_schedule_data (mock fallback)
│       └── utils.py          — decode_am_jwt, get_role_name, _auth_headers
│
├── frontend/
│   └── src/
│       ├── App.jsx       — Chat UI, sidebar, SSE reader, file upload
│       └── Auth.jsx      — Login / register form
│
├── .env                  — Environment variables
├── requirements.txt      — Python dependencies
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

# AllMasters AES encryption key (same as AM frontend CryptoJS key)
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
| `messages` | All messages per chat (user / assistant / tool / assistant_tool_call) |
| `sessions` | AllMasters JWT stored per `(user_id, chat_id)` |

---

## Two-JWT System

### 1. App JWT
- Issued by our FastAPI on register/login
- Signs with `JWT_SECRET_KEY` (HS256)
- Protects all `/chat/*` endpoints via `Authorization: Bearer <token>`
- Stored in browser `localStorage`

### 2. AllMasters (AM) JWT
- Obtained by calling the MCP `authenticate` tool with AM credentials
- Stored in `sessions` table keyed by `(user_id, chat_id)`
- Automatically injected into tool calls that require it
- Never exposed in the SSE stream to the frontend

---

## MCP Tools (5 total)

| Tool | Auth Required | Description |
|---|---|---|
| `authenticate` | No | Calls `getUserRoles` for dynamic type, AES-encrypts password, calls AM `/user/login`. Handles "already logged in" by auto-logout + retry. |
| `search_schedule` | No | Port-to-port vessel schedule search. Has mock fallback if AM API unreachable. |
| `get_booking_status` | AM JWT | Fetches booking status from AM API. |
| `get_milestones` | AM JWT | Fetches next pending milestone (status=0), checks role access, returns `isAccess` + `requiredFields`. |
| `update_milestone` | AM JWT | Role check → portal check → field validation → POST to AM. |

**Auth-required tools** are defined in `chat_engine.py`:
```python
AUTH_REQUIRED_TOOLS = {"get_booking_status", "get_milestones", "update_milestone"}
```
If no AM JWT in session → engine blocks the call and tells LLM to ask for credentials.

---

## Authentication Flow (AM Login)

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
- Calls `GET /milestone/getRefineMilestoneByAMBookingId`
- Finds **first pending milestone** (`milestoneStatus == 0`)
- Decodes AM JWT to get user role
- Checks `milestoneActionRole` vs user role → sets `isAccess`
- Returns enriched milestone:
  - `isAccess: true` → includes `requiredFields` from local config
  - `isAccess: false` → includes `actionRoleNames`, empty `requiredFields`

### update_milestone
- Fetches milestone via `getRefineMilestoneByBookingId`
- Role check → portal check (`shouldPerformOnAm`) → field validation → file validation
- Posts to `/milestone/milestoneRefine`

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
| Booking / milestones, no AM session | Asks for AM email + password, calls `authenticate` |
| `isAccess: false` on milestone | Tells user who can update it, does NOT collect fields |
| `isAccess: true`, no required fields | Asks confirmation, calls `update_milestone` |
| `isAccess: true`, has required fields | Collects each field conversationally (text/date via chat, file via upload button), confirms, calls `update_milestone` |
| `portal_required: true` | Tells user to complete on AllMasters portal |

---

## API Endpoints

### Public
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Login, returns app JWT |
| GET | `/health` | Health check |

### Protected (requires app JWT)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/chat/new` | Create new chat session |
| POST | `/chat` | Send message — SSE stream response |
| GET | `/chat/list` | List all chats for user |
| GET | `/chat/{chat_id}/history` | Load chat history |
| DELETE | `/chat/{chat_id}` | Clear chat + AM session |
| POST | `/milestones` | Direct milestone fetch (called by AM portal with AM JWT) |

---

## SSE Event Types

| Event type | When |
|---|---|
| `token` | LLM is streaming a text chunk |
| `tool_call` | A tool is being called (JWT stripped from payload) |
| `tool_result` | Tool returned a result |
| `done` | Response complete |
| `error` | Something went wrong |

---

## Known Issues / Notes

- **MCP subprocess + VS Code debugpy**: Never use `print()` inside MCP server tools. Both `stdout` (breaks JSON-RPC) and `stderr` (hijacked by debugpy) are unusable. Use a log file if debugging is needed.
- **AM JWT expiry**: JWT has ~1 hour window (`exp` field). Expired JWTs are not checked before use — AM API will return 401. Re-authentication is not automatic.
- **File upload validation**: `update_milestone` validates file count (`len(file_uploads) >= len(file_fields)`). Files are passed as base64 from frontend.

---

## Running the Project

### Backend
```bash
cd am-chatbot
pip install -r requirements.txt
uvicorn chatbot.api:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
