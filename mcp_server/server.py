"""
mcp_server/server.py
=====================
AllMasters MCP Server — exposes tools via MCP protocol (stdio transport).
The chatbot's chat_engine connects to this as an MCP client.

Run standalone (for testing):
    python mcp_server/server.py

The chat_engine starts this automatically as a subprocess per request.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp.server.fastmcp import FastMCP
from mcp_server.tools.auth       import authenticate_user
from mcp_server.tools.schedule   import search_schedule_data
from mcp_server.tools.booking    import get_booking_status_data
from mcp_server.tools.milestones import get_milestones, update_milestone

mcp = FastMCP("am-mcp-server")


# ── Public Tools (no auth) ────────────────────────────────────────────────────

@mcp.tool()
def authenticate(username: str, password: str) -> dict:
    """
    Authenticate the user with AllMasters credentials.
    Call this when the user provides their username and password.
    Returns a JWT token on success.
    """
    return authenticate_user(username, password)


@mcp.tool()
def search_schedule(pol: str, pod: str) -> dict:
    """
    Search AllMasters vessel schedules between two ports.
    No authentication required. Pass the port name exactly as the user provided it.
    """
    return search_schedule_data(pol, pod)


# ── Auth-Required Tools ───────────────────────────────────────────────────────

@mcp.tool()
def get_booking_status(booking_number: str, jwt: str) -> dict:
    """
    Get the current status of an AllMasters booking.
    Requires authentication — jwt must be a valid AllMasters token.
    """
    return get_booking_status_data(booking_number, jwt)


@mcp.tool()
def get_milestones(booking_id: str, jwt: str) -> dict:
    """
    Get all milestone steps for a booking from AllMasters.
    Returns each milestone with status, action/view roles, required fields, and current data.
    Requires authentication — jwt must be a valid AllMasters token.
    """
    from mcp_server.tools.milestones import get_milestones as _get
    return _get(jwt, booking_id)


@mcp.tool()
def update_milestone(booking_id: str, milestone_name: str, collected_data: dict, jwt: str, file_uploads: list = None) -> dict:
    """
    Update a specific milestone for a booking.
    - milestone_name: the milestoneName value (e.g. 'containerSealno', 'onboardConfirmation')
    - collected_data: dict of text/date field values collected from the user via chat
    - file_uploads: list of { fileName, filePath (base64), fileLabel } — from user file attachments in chat
    - Checks user role permission before proceeding.
    - If shouldPerformOnAm is True in config, tells user to proceed via AllMasters portal.
    Requires authentication — jwt must be a valid AllMasters token.
    """
    from mcp_server.tools.milestones import update_milestone as _update
    return _update(jwt, booking_id, milestone_name, collected_data, file_uploads)


if __name__ == "__main__":
    mcp.run()  # stdio transport — communicates via stdin/stdout
