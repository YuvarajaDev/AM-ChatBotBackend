"""
mcp_server/tools/schedule.py
=============================
Schedule search tool — public, no auth required.
Real API call + mock fallback.
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

AM_API_BASE_URL = os.getenv("AM_API_BASE_URL", "http://localhost:3000")


def search_schedule_data(pol: str, pod: str) -> dict:
    try:
        r = requests.post(
            f"{AM_API_BASE_URL}/schedule/getSchedulesByPortName",
            json={"data": [{"pol": pol, "pod": pod}]},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"  [Schedule] API unreachable, using mock. Reason: {e}", file=sys.stderr)
        return _mock_schedules(pol, pod)


def _mock_schedules(pol: str, pod: str) -> dict:
    return {
        "pol": pol,
        "pod": pod,
        "schedules": [
            {
                "vessel": "AM STAR",
                "voyage": "AM-101",
                "etd": "2026-04-15",
                "eta": "2026-04-30",
                "transit_days": 15,
                "available_slots": 80,
                "carrier": "AllMasters Line"
            },
            {
                "vessel": "AM FALCON",
                "voyage": "AM-202",
                "etd": "2026-04-22",
                "eta": "2026-05-07",
                "transit_days": 15,
                "available_slots": 45,
                "carrier": "AllMasters Line"
            },
            {
                "vessel": "AM HORIZON",
                "voyage": "AM-303",
                "etd": "2026-04-29",
                "eta": "2026-05-14",
                "transit_days": 15,
                "available_slots": 120,
                "carrier": "AllMasters Line"
            }
        ]
    }
