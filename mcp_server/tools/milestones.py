"""
mcp_server/tools/milestones.py
================================
Milestone tools — get milestones and update a milestone.
Handles role-based access check before any update.
"""

import os
import json
import requests
from dotenv import load_dotenv

from .utils import decode_am_jwt, get_role_name, _auth_headers
from .milestone_config import get_milestone_config, should_perform_on_am, get_text_fields, get_file_fields

load_dotenv()

AM_API_BASE_URL = os.getenv("AM_API_BASE_URL", "http://localhost:3000")


# ── Internal helper ────────────────────────────────────────────────────────────

def _fetch_all_milestones(jwt: str, booking_id: str) -> tuple:
    """
    Fetch raw milestone list + booking data from AM API.
    Returns (milestones_list, data_dict). Not exposed to the LLM.
    """
    r = requests.post(
        f"{AM_API_BASE_URL}/milestone/getRefineMilestoneByAMBookingId",
        json={"data": [{"bookingId": booking_id, "isEncryptionRequired": False}]},
        headers=_auth_headers(jwt),
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    data = json.loads(body.get("data", "{}"))
    return data.get("milestone", []), data


# ── Get Milestones ─────────────────────────────────────────────────────────────

def get_milestones(jwt: str, booking_id: str) -> dict:
    """
    Fetch milestones for a booking from AM API and merge with local config.
    Returns the first pending milestone enriched with requiredFields and access info.
    """
    try:
        milestones, data = _fetch_all_milestones(jwt, booking_id)
        if not milestones:
            return {"success": False, "message": "No milestones found for this booking."}

        # Decode user role for config lookup
        user_info = decode_am_jwt(jwt)
        user_role = user_info.get("role")

        # Find the first pending (status == 0) milestone
        next_m = next((m for m in milestones if m.get("milestoneStatus", 0) == 0), None)
        if not next_m:
            return {"success": True, "data": {
                "bookingId": booking_id, "milestones": [],
                "message": "All milestones completed for this booking."
            }}

        name         = next_m.get("milestoneName", "")
        action_roles = next_m.get("milestoneActionRole", [])
        cfg          = get_milestone_config(name, user_role)

        # Empty action_roles means any role can update
        is_access = (not action_roles) or (user_role in action_roles)

        enriched = [{
            "milestoneName":       name,
            "milestoneLabelName":  next_m.get("milestoneLabelName", ""),
            "milestoneStatus":     next_m.get("milestoneStatus", 0),
            "milestoneActionRole": action_roles,
            "milestoneViewRole":   next_m.get("milestoneViewRole", []),
            "milestoneData":       next_m.get("milestoneData", {}),
            "isSkip":              next_m.get("isSkip", 0),
            "_id":                 next_m.get("_id", ""),
            "bookingId":          booking_id,
            # access info
            "isAccess":            is_access,
            "actionRoleNames":     [get_role_name(r) for r in action_roles] if not is_access else [],
            # config — only expose required fields when user has access
            "requiredFields":      cfg.get("requiredFields", []) if is_access else [],
            "isFileUpload":        cfg.get("isFileUpload", False),
            "proceedMileStone":    cfg.get("proceedMileStone", False),
            "instruction":         cfg.get("instruction", None),
        }]

        finalData = {
            "bookingId": booking_id,
            'AMSBy': data.get("AMSBy", ""),
            'ocfsId': data.get("ocfsId", ""),
            'inlandOcfsId': data.get("inlandOcfsId", ""),
            'dcfsId': data.get("dcfsId", ""),
            'inlandDcfsId': data.get("inlandDcfsId", ""),
            'bookingStatus': data.get("bookingStatus", 0),
            'isCollectChargeAvail': data.get("isCollectChargeAvail", 0),
            'bookingFlow': data.get("bookingFlow", 0),
            'blTerm': data.get("blTerm", ""),
            'blType': data.get("blType", ""),
            'bookingObjId': data.get("bookingId", ""),
            "milestones": enriched,
        }
        return {"success": True, "data": finalData}

    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Failed to fetch milestones: {e}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {e}"}


# ── Update Milestone ───────────────────────────────────────────────────────────

def update_milestone(jwt: str, booking_id: str, milestone_name: str, collected_data: dict = None, file_uploads: list = None) -> dict:
    """
    Update a milestone after role check.

    Flow:
      1. Decode JWT → userId, userRole
      2. Fetch all milestones from AM API (single call via helper)
      3. Check milestoneActionRole vs userRole
      4. If portal-only → redirect message
      5. Validate collected text/date fields
      6. Build payload (+ revisedMeasurment skip for surveyCompleted)
      7. POST update to AM API
    """
    collected_data = collected_data or {}
    file_uploads   = file_uploads   or []

    # 1. Decode JWT
    user_info = decode_am_jwt(jwt)
    user_role = user_info.get("role")
    user_id   = user_info.get("userId")

    if not user_role or not user_id:
        return {"success": False, "message": "Invalid session. Please authenticate again."}

    # 2. Fetch all milestones (single API call — raw list used for target + companion updates)
    try:
        all_milestones, data = _fetch_all_milestones(jwt, booking_id)
    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Failed to fetch milestone data: {e}"}

    milestoneObjBookingId = data.get("bookingId", "")

    milestone = next((m for m in all_milestones if m.get("milestoneName") == milestone_name), None)
    if not milestone:
        return {"success": False, "message": f"Milestone '{milestone_name}' not found for this booking."}

    # 3. Role access check
    action_roles = milestone.get("milestoneActionRole", [])
    if action_roles and user_role not in action_roles:
        role_names = [get_role_name(r) for r in action_roles]
        return {
            "success":      False,
            "access_denied": True,
            "message": (
                f"You don't have permission to update this milestone. "
                f"It can only be performed by: {', '.join(role_names)}. Please wait for them to proceed."
            ),
        }

    # 4. Check if this milestone must be performed on AllMasters portal
    if should_perform_on_am(milestone_name, user_role):
        return {
            "success": False,
            "portal_required": True,
            "message": (
                f"The '{milestone.get('milestoneLabelName', milestone_name)}' milestone needs to be completed "
                f"via the AllMasters portal. Please proceed there."
            ),
        }

    # 5. Validate required text/date fields
    text_fields = get_text_fields(milestone_name, user_role)
    missing     = [f for f in text_fields if not collected_data.get(f["name"])]
    if missing:
        missing_labels = [f["label"] for f in missing]
        return {
            "success":        False,
            "missing_fields": missing_labels,
            "message":        f"Please provide the following: {', '.join(missing_labels)}",
        }

    # 5b. Validate file fields — must be provided by user via chat upload
    file_fields = get_file_fields(milestone_name, user_role)

    # Frontend sets fileLabel from the upload filename, which won't match the
    # required field name. Rewrite each upload's fileLabel to the required
    # field name so validation + downstream AM API get the expected key.
    if file_fields and file_uploads:
        target_name = file_fields[0]["name"]
        for fu in file_uploads:
            fu["fileLabel"] = target_name

    provided_names = {f.get("fileLabel") for f in file_uploads}
    missing_files  = [f for f in file_fields if f["name"] not in provided_names]
    if missing_files:
        missing_labels = [f["label"] for f in missing_files]
        return {
            "success":        False,
            "missing_files":  missing_labels,
            "message":        f"Please upload the required file(s): {', '.join(missing_labels)}",
        }

    # 6. Build update payload — spread milestone object + required fields
    milestone_id   = milestone.get("_id", "")
    update_payload = {"data": [{
        **milestone,
        "milestoneBy":     user_id,
        "userRole":        user_role,
        "bookingId":       milestoneObjBookingId,
        "milestoneStatus": 1,  # mark as completed
        "milestoneStepId": milestone_id,
        "milestoneData":   collected_data,
        "fileUpload":      file_uploads,  # [{ fileName, filePath (base64), fileLabel }]
        "isEncryptionRequired": False,
    }]}

    # surveyCompleted: always skip revisedMeasurment in the same API call
    if milestone_name == "surveyCompleted":
        revised = next((m for m in all_milestones if m.get("milestoneName") == "revisedMeasurment"), None)
        if revised:
            update_payload["data"].append({
                **revised,
                "milestoneBy":     user_id,
                "userRole":        user_role,
                "bookingId":       milestoneObjBookingId,
                "milestoneStatus": 2,
                "milestoneStepId": revised.get("_id", ""),
                "isSkip":          1,
                "milestoneData":   {},
                "fileUpload":      [],
                "isEncryptionRequired": False,
            })

    # 7. Call AM update API
    try:
        r = requests.post(
            f"{AM_API_BASE_URL}/milestone/milestoneRefine",
            json=update_payload,
            headers=_auth_headers(jwt),
            timeout=10,
        )
        r.raise_for_status()
        print(f"update status {r.status_code}, response: {r.text}")
        return {
            "success": True,
            "message": f"Milestone '{milestone.get('milestoneLabelName', milestone_name)}' updated successfully.",
        }
    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Failed to update milestone: {e}"}
