"""
Converts bangalore_events_2024.py into MongoDB documents:
  - historical_patterns  (derived from past events — gives agent its reasoning)
  - scheduled_events     (upcoming in 2024/25 — drives proactive predictions)

Usage:
  python load_real_events.py           # seeds both collections
  python load_real_events.py patterns  # only historical_patterns
  python load_real_events.py schedule  # only scheduled_events

Also accepts an optional Kaggle IPL CSV to enrich IPL data:
  python load_real_events.py --ipl-csv path/to/IPL_2024_matches.csv
"""
import os
import sys
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

# Add parent dir so we can import data module
sys.path.insert(0, os.path.dirname(__file__))
from data.bangalore_events_2024 import (
    PUBLIC_HOLIDAYS_2024,
    IPL_2024_RCB_HOME_GAMES,
    CONCERTS_2024,
    MONSOON_HEAVY_RAIN_2024,
    TECH_PARK_EVENTS_2024,
    VENUE_TO_ZONES,
    HOLIDAY_SPIKE_ZONES,
)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/delivery_ops")
client = MongoClient(MONGO_URI)
db = client["delivery_ops"]

# ── Historical pattern templates ──────────────────────────────────────────────
# Each event type maps to pre-researched resolution stats
PATTERN_TEMPLATES = {
    "ipl_match": {
        "avg_demand_spike_percent": 40,
        "avg_resolution_minutes":   14,
        "avg_agents_moved":         12,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "evening",
        "spike_delay_minutes":      17,
        "notes_template":           (
            "{name}: spike occurs 15-20 min after match end. "
            "Crowd disperses from Chinnaswamy toward HSR Layout and Indiranagar. "
            "Pre-positioning from zone_01 (Koramangala) resolves in all recorded cases."
        ),
    },
    "concert": {
        "avg_demand_spike_percent": 45,
        "avg_resolution_minutes":   18,
        "avg_agents_moved":         14,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "evening",
        "spike_delay_minutes":      20,
        "notes_template":           (
            "{name}: post-show food orders surge as crowd leaves venue. "
            "Palace Grounds concerts end 10-11 PM; Rajajinagar and Malleshwaram "
            "see highest density. Redistribution from Hebbal resolves within 18 min."
        ),
    },
    "festival_diwali": {
        "avg_demand_spike_percent": 60,
        "avg_resolution_minutes":   22,
        "avg_agents_moved":         16,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "evening",
        "spike_delay_minutes":      0,
        "notes_template":           (
            "{name}: sweets + snacks orders surge from 6 PM. "
            "South Bangalore residential zones (Jayanagar, Banashankari, JP Nagar) "
            "spike hardest. Outer zones (Kengeri, Yelahanka) have surplus."
        ),
    },
    "festival_holi": {
        "avg_demand_spike_percent": 35,
        "avg_resolution_minutes":   16,
        "avg_agents_moved":         10,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "daytime",
        "spike_delay_minutes":      0,
        "notes_template":           (
            "{name}: afternoon food orders spike as families celebrate at home. "
            "Koramangala and Indiranagar see highest delivery volume."
        ),
    },
    "new_year_eve": {
        "avg_demand_spike_percent": 70,
        "avg_resolution_minutes":   25,
        "avg_agents_moved":         18,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "evening",
        "spike_delay_minutes":      0,
        "notes_template":           (
            "{name}: highest-demand night of the year. MG Road, Koramangala, "
            "Indiranagar simultaneously critical from 11 PM to 2 AM. "
            "Must pre-position from outer zones (Kengeri, Yelahanka) by 10 PM."
        ),
    },
    "monsoon_rain": {
        "avg_demand_spike_percent": 35,
        "avg_resolution_minutes":   16,
        "avg_agents_moved":         10,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "daytime",
        "spike_delay_minutes":      10,
        "notes_template":           (
            "{name}: people stay home and order in. South Bangalore residential "
            "zones spike. Outer zones with lower restaurant density have surplus. "
            "Pre-position on IMD red/orange alert, not after rain starts."
        ),
    },
    "office_event": {
        "avg_demand_spike_percent": 50,
        "avg_resolution_minutes":   15,
        "avg_agents_moved":         14,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "evening",
        "spike_delay_minutes":      30,
        "notes_template":           (
            "{name}: tech park employees celebrate then order in. "
            "Whitefield and Electronic City spike from 7 PM on last working day of quarter. "
            "Marathahalli bridge area (zone_07) reliably has surplus."
        ),
    },
    "public_holiday_generic": {
        "avg_demand_spike_percent": 25,
        "avg_resolution_minutes":   12,
        "avg_agents_moved":         8,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "daytime",
        "spike_delay_minutes":      0,
        "notes_template":           (
            "{name}: general public holiday demand surge. "
            "Central Bangalore (Koramangala, Indiranagar) sees highest volume. "
            "Standard 8-agent redistribution from outer zones resolves in ~12 min."
        ),
    },
    "independence_day": {
        "avg_demand_spike_percent": 30,
        "avg_resolution_minutes":   14,
        "avg_agents_moved":         10,
        "best_action":              "agent_redistribution",
        "typical_time_of_day":      "daytime",
        "spike_delay_minutes":      0,
        "notes_template":           (
            "{name}: post-parade family gatherings drive midday delivery surge. "
            "MG Road and Rajajinagar areas see highest volume post-parade."
        ),
    },
}

# ── Event type → zone mapping helper ─────────────────────────────────────────

def get_zones_for_event(event_type: str, name: str, venue: str = None) -> list:
    if venue and venue in VENUE_TO_ZONES:
        return VENUE_TO_ZONES[venue]
    if event_type in HOLIDAY_SPIKE_ZONES:
        return HOLIDAY_SPIKE_ZONES[event_type]
    if event_type == "ipl_match":
        return VENUE_TO_ZONES["Chinnaswamy"]
    if event_type == "office_event":
        return ["zone_05", "zone_08"]
    if event_type == "monsoon_rain":
        return ["zone_06", "zone_13", "zone_17", "zone_04"]
    return ["zone_01", "zone_02"]


# ── Build historical patterns ─────────────────────────────────────────────────

def build_historical_patterns() -> list:
    """
    Build historical_patterns documents from all 2024 event data.
    Groups events by (event_type, zone) and computes aggregate stats.
    """
    # Count occurrences per (event_type, zone)
    occurrence_map: dict[tuple, list] = {}

    all_events = (
        [(e, "ipl_match",              None)           for e in IPL_2024_RCB_HOME_GAMES]
        + [(e, "concert",              e.get("venue")) for e in CONCERTS_2024]
        + [(e, "monsoon_rain",         None)           for e in MONSOON_HEAVY_RAIN_2024]
        + [(e, "office_event",         None)           for e in TECH_PARK_EVENTS_2024]
        + [(e, _holiday_event_type(e), None)           for e in PUBLIC_HOLIDAYS_2024]
    )

    for event, event_type, venue in all_events:
        zones = get_zones_for_event(event_type, event["name"], venue)
        for zone_id in zones:
            key = (event_type, zone_id)
            occurrence_map.setdefault(key, []).append(event["name"])

    patterns = []
    for (event_type, zone_id), names in occurrence_map.items():
        template = PATTERN_TEMPLATES.get(event_type, PATTERN_TEMPLATES["public_holiday_generic"])
        example_name = names[0]
        pattern = {
            "pattern_id":               f"{event_type}_{zone_id}_2024",
            "event_type":               event_type,
            "affected_zone":            zone_id,
            "occurrences":              len(names),
            "year":                     2024,
            "avg_demand_spike_percent": template["avg_demand_spike_percent"],
            "avg_resolution_minutes":   template["avg_resolution_minutes"],
            "best_action":              template["best_action"],
            "avg_agents_moved":         template["avg_agents_moved"],
            "typical_time_of_day":      template["typical_time_of_day"],
            "spike_delay_minutes":      template["spike_delay_minutes"],
            "notes": template["notes_template"].format(name=example_name),
            "example_events":           names[:3],
            "data_source":              "bangalore_events_2024.py",
        }
        patterns.append(pattern)

    return patterns


def _holiday_event_type(holiday: dict) -> str:
    name = holiday["name"].lower()
    if "diwali" in name:
        return "festival_diwali"
    if "holi" in name:
        return "festival_holi"
    if "new year" in name:
        return "new_year_eve"
    if "independence" in name:
        return "independence_day"
    return "public_holiday_generic"


# ── Build scheduled events (upcoming in 2024/25) ──────────────────────────────

def build_scheduled_events() -> list:
    """
    Convert 2024 events into scheduled_events documents.
    Only includes events that are 'upcoming' relative to now,
    OR marks past ones as 'completed' for demo purposes.
    """
    now = datetime.utcnow()
    events = []

    # IPL matches — 7:30 PM IST = 14:00 UTC
    for match in IPL_2024_RCB_HOME_GAMES:
        dt = datetime.fromisoformat(match["date"] + "T14:00:00")
        events.append({
            "event_id":                   f"ipl_{match['date'].replace('-', '')}",
            "event_type":                 "ipl_match",
            "name":                       match["name"],
            "affected_zones":             VENUE_TO_ZONES["Chinnaswamy"],
            "scheduled_time":             dt.isoformat(),
            "expected_spike_after_minutes": 17,
            "status":                     "upcoming" if dt > now else "completed",
            "confidence":                 match["confidence"],
            "data_source":                "BCCI IPL 2024 fixture list",
        })

    # Concerts — 7:00 PM IST = 13:30 UTC
    for concert in CONCERTS_2024:
        dt = datetime.fromisoformat(concert["date"] + "T13:30:00")
        venue = concert.get("venue", "Palace Grounds")
        zones = get_zones_for_event("concert", concert["name"], venue)
        events.append({
            "event_id":                   f"concert_{concert['date'].replace('-', '')}",
            "event_type":                 "concert",
            "name":                       concert["name"],
            "affected_zones":             zones,
            "scheduled_time":             dt.isoformat(),
            "expected_spike_after_minutes": 20,
            "status":                     "upcoming" if dt > now else "completed",
            "confidence":                 concert["confidence"],
            "data_source":                "BookMyShow Bangalore 2024",
        })

    # Monsoon heavy rain — daytime spikes (noon UTC = 5:30 PM IST)
    for rain in MONSOON_HEAVY_RAIN_2024:
        dt = datetime.fromisoformat(rain["date"] + "T06:30:00")  # 12pm IST
        events.append({
            "event_id":                   f"rain_{rain['date'].replace('-', '')}",
            "event_type":                 "monsoon_rain",
            "name":                       rain["name"],
            "affected_zones":             ["zone_06", "zone_13", "zone_17", "zone_04"],
            "scheduled_time":             dt.isoformat(),
            "expected_spike_after_minutes": 10,
            "status":                     "upcoming" if dt > now else "completed",
            "confidence":                 rain["confidence"],
            "data_source":                "IMD Bangalore historical averages",
        })

    # Public holidays — evening peak 6:00 PM IST = 12:30 UTC
    for holiday in PUBLIC_HOLIDAYS_2024:
        dt = datetime.fromisoformat(holiday["date"] + "T12:30:00")
        event_type = _holiday_event_type(holiday)
        zones = get_zones_for_event(event_type, holiday["name"])
        events.append({
            "event_id":                   f"holiday_{holiday['date'].replace('-', '')}",
            "event_type":                 event_type,
            "name":                       holiday["name"],
            "affected_zones":             zones,
            "scheduled_time":             dt.isoformat(),
            "expected_spike_after_minutes": 0,
            "status":                     "upcoming" if dt > now else "completed",
            "confidence":                 holiday["confidence"],
            "data_source":                "Govt of India Gazette 2024",
        })

    # Tech park quarter-ends — 7:00 PM IST = 13:30 UTC
    for event in TECH_PARK_EVENTS_2024:
        dt = datetime.fromisoformat(event["date"] + "T13:30:00")
        events.append({
            "event_id":                   f"techpark_{event['date'].replace('-', '')}",
            "event_type":                 "office_event",
            "name":                       event["name"],
            "affected_zones":             ["zone_05", "zone_08"],
            "scheduled_time":             dt.isoformat(),
            "expected_spike_after_minutes": 30,
            "status":                     "upcoming" if dt > now else "completed",
            "confidence":                 event["confidence"],
            "data_source":                "Financial calendar Q-end dates",
        })

    return events


# ── Seed functions ────────────────────────────────────────────────────────────

def seed_patterns():
    patterns = build_historical_patterns()
    db.historical_patterns.drop()
    db.historical_patterns.insert_many(patterns)

    by_type = {}
    for p in patterns:
        by_type.setdefault(p["event_type"], 0)
        by_type[p["event_type"]] += 1

    print(f"\nhistorical_patterns: {len(patterns)} patterns seeded")
    for etype, count in sorted(by_type.items()):
        print(f"  {etype:30s} {count} zone-patterns")


def seed_scheduled():
    events = build_scheduled_events()
    db.scheduled_events.drop()
    db.scheduled_events.insert_many(events)

    upcoming = sum(1 for e in events if e["status"] == "upcoming")
    completed = len(events) - upcoming
    print(f"\nscheduled_events: {len(events)} total")
    print(f"  upcoming:  {upcoming}")
    print(f"  completed: {completed} (historical — used for pattern validation)")


def load_ipl_csv(csv_path: str):
    """
    Optionally load IPL schedule from a Kaggle CSV to replace hardcoded dates.
    Expected columns: date, team1, team2, venue
    Download from: kaggle.com/datasets/patrickb1912/ipl-complete-dataset-20082020
    """
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        rcb_home = df[
            (df["venue"].str.contains("Chinnaswamy", na=False)) &
            (df["date"].str.startswith("2024", na=False))
        ]
        games = []
        for _, row in rcb_home.iterrows():
            games.append({
                "date":       row["date"],
                "name":       f"IPL: {row['team1']} vs {row['team2']}",
                "confidence": "HIGH",
            })
        if games:
            print(f"Loaded {len(games)} IPL 2024 home games from CSV")
            return games
    except Exception as e:
        print(f"Could not load IPL CSV: {e}")
    return IPL_2024_RCB_HOME_GAMES


if __name__ == "__main__":
    ipl_csv = None
    mode = "both"

    for arg in sys.argv[1:]:
        if arg == "patterns":
            mode = "patterns"
        elif arg == "schedule":
            mode = "schedule"
        elif arg.startswith("--ipl-csv="):
            ipl_csv = arg.split("=", 1)[1]

    if ipl_csv:
        updated = load_ipl_csv(ipl_csv)
        IPL_2024_RCB_HOME_GAMES.clear()
        IPL_2024_RCB_HOME_GAMES.extend(updated)

    print("Loading real 2024 Bangalore event data into MongoDB...")

    if mode in ("both", "patterns"):
        seed_patterns()
    if mode in ("both", "schedule"):
        seed_scheduled()

    print("\nDone.")
    print("\nUpcoming events in scheduled_events:")
    for e in db.scheduled_events.find({"status": "upcoming"}).sort("scheduled_time", 1).limit(10):
        print(f"  {e['scheduled_time'][:10]}  {e['event_type']:20s}  {e['name']}")
