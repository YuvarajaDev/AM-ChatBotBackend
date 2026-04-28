"""
mcp_server/tools/utils.py
=========================
Shared utilities — AM JWT decoding, role helpers.
"""

import jwt as pyjwt

ROLE_NAMES = {
    1: "User",
    2: "Admin",
    3: "OBT",
    4: "RDT",
    5: "OT",
    6: "Origin CFS",
    7: "Destination CFS",
}


def decode_am_jwt(token: str) -> dict:
    """
    Decode AM JWT without signature verification (we don't have AM's secret).
    Returns { userId, role, type, status }.
    """
    try:
        payload = pyjwt.decode(token, options={"verify_signature": False})
        return {
            "userId": payload.get("userId"),
            "role":   payload.get("role"),
            "type":   payload.get("type"),
            "status": payload.get("status"),
        }
    except Exception:
        return {}


def get_role_name(role_id: int) -> str:
    return ROLE_NAMES.get(role_id, f"Role {role_id}")


def _auth_headers(jwt: str) -> dict:
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
