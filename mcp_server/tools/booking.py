"""
mcp_server/tools/booking.py
============================
Booking status tool — requires authentication.
Real API call + mock fallback.
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

AM_API_BASE_URL = os.getenv("AM_API_BASE_URL", "http://localhost:3000")


def get_booking_status_data(booking_number: str, jwt: str) -> dict:
    try:
        r = requests.post(
            f"{AM_API_BASE_URL}/milestone/getBookingStatusByBId",
            headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
            json={"data": [{"bId": booking_number, "isEncryptionRequired": False}]},
            timeout=10
        )
        r.raise_for_status()
        body = r.json()
        data = body.get("data", {})
        schedule = data.get("schedule", {})
        return {
            "success": True,
            "bId": data.get("bId"),
            "scheduleId": schedule.get("scheduleId"),
            "vessel": schedule.get("vessel"),
            "voyage": schedule.get("voyage"),
            "currentMilestone": data.get("currentMilestone"),
            "nextMilestone": data.get("nextMilestone"),
            "completedSteps": data.get("completedSteps"),
            "totalSteps": data.get("totalSteps"),
        }
    except requests.exceptions.RequestException as e:
        print(f"  [Booking] API unreachable, using mock. Reason: {e}", file=sys.stderr)
        return {"success": False, "message": "Unable to fetch booking status from AllMasters API."}
    except Exception as e:
        # return _mock_booking(booking_number)
        return {"success": False, "message": "An unexpected error occurred."}


# def _mock_booking(booking_number: str) -> dict:
#     return {
#         "booking_number": booking_number,
#         "status": "IN_TRANSIT",
#         "booking_type": "FCL",
#         "vessel": "AM STAR",
#         "voyage": "AM-101",
#         "pol": "SGSIN",
#         "pol_name": "Singapore",
#         "pod": "INNSA",
#         "pod_name": "Nhava Sheva",
#         "etd": "2026-04-15",
#         "eta": "2026-04-30",
#         "container_type": "20GP",
#         "container_count": 2,
#         "shipper": "ABC Exports Pte Ltd"
#     }
