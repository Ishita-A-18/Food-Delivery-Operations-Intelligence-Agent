"""
Pre-event predictor — creates a scheduled_event so the agent proposes
pre-emptive redistribution BEFORE the spike hits.

Usage:
  python predict_spike.py                     # IPL match in 45 min (default)
  python predict_spike.py ipl 45
  python predict_spike.py concert 30
  python predict_spike.py new_year 120
  python predict_spike.py monsoon 20
  python predict_spike.py techpark 60
  python predict_spike.py diwali 90

Demo sequence:
  1. python predict_spike.py <event_type>   ← agent proposes PROACTIVE pre-positioning
  2. Approve the card on the dashboard
  3. python inject_spike.py <trigger_id>    ← actual spike hits, zone handles it better
"""
import os
import sys
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/delivery_ops")
client = MongoClient(MONGO_URI)
db = client["delivery_ops"]

EVENTS = {
    "ipl": {
        "event_id":                   "ipl_rcb_mi",
        "event_type":                 "ipl_match",
        "name":                       "IPL: RCB vs MI at Chinnaswamy Stadium",
        "affected_zones":             ["zone_02", "zone_03"],
        "expected_spike_after_minutes": 15,
        "inject_trigger":             "ipl_spike",
    },
    "concert": {
        "event_id":                   "concert_palace_grounds",
        "event_type":                 "concert",
        "name":                       "Coldplay Concert at Palace Grounds",
        "affected_zones":             ["zone_10", "zone_11"],
        "expected_spike_after_minutes": 20,
        "inject_trigger":             "concert_spike",
    },
    "new_year": {
        "event_id":                   "new_year_eve_bangalore",
        "event_type":                 "new_year_eve",
        "name":                       "New Year's Eve — MG Road & Koramangala",
        "affected_zones":             ["zone_18", "zone_01", "zone_03"],
        "expected_spike_after_minutes": 0,
        "inject_trigger":             "new_year_spike",
    },
    "monsoon": {
        "event_id":                   "monsoon_heavy_rain",
        "event_type":                 "monsoon_rain",
        "name":                       "Heavy Rain Alert — Bangalore South & Central",
        "affected_zones":             ["zone_06", "zone_13", "zone_17", "zone_04"],
        "expected_spike_after_minutes": 10,
        "inject_trigger":             "monsoon_spike",
    },
    "techpark": {
        "event_id":                   "techpark_quarter_end",
        "event_type":                 "office_event",
        "name":                       "Q4 End Celebrations — Whitefield & Electronic City",
        "affected_zones":             ["zone_05", "zone_08"],
        "expected_spike_after_minutes": 30,
        "inject_trigger":             "techpark_spike",
    },
    "diwali": {
        "event_id":                   "diwali_2024",
        "event_type":                 "festival_diwali",
        "name":                       "Diwali Night — South Bangalore Residential Zones",
        "affected_zones":             ["zone_06", "zone_09", "zone_17"],
        "expected_spike_after_minutes": 0,
        "inject_trigger":             "diwali_spike",
    },
}


def schedule_event(event_key: str = "ipl", minutes_from_now: int = 45):
    if event_key not in EVENTS:
        print(f"Unknown event type '{event_key}'. Choose from: {', '.join(EVENTS)}")
        sys.exit(1)

    event = EVENTS[event_key]
    scheduled_time = (datetime.utcnow() + timedelta(minutes=minutes_from_now)).isoformat()

    db.scheduled_events.replace_one(
        {"event_id": event["event_id"]},
        {
            **event,
            "scheduled_time":  scheduled_time,
            "status":          "upcoming",
            "created_at":      datetime.utcnow().isoformat(),
        },
        upsert=True,
    )

    zone_names = []
    for zid in event["affected_zones"]:
        z = db.city_grid.find_one({"zone_id": zid}, {"name": 1})
        zone_names.append(z["name"] if z else zid)

    print(f"\nScheduled: {event['name']}")
    print(f"  Event type   : {event['event_type']}")
    print(f"  Starts in    : {minutes_from_now} min (UTC: {scheduled_time})")
    print(f"  Affected zones: {', '.join(zone_names)}")
    print(f"\nAgent detects this on next tick (~60s) → PROACTIVE approval card appears.")
    print(f"After approving, run:  python inject_spike.py {event['inject_trigger']}")


if __name__ == "__main__":
    event_key      = sys.argv[1] if len(sys.argv) > 1 else "ipl"
    minutes        = int(sys.argv[2]) if len(sys.argv) > 2 else 45
    schedule_event(event_key, minutes)
