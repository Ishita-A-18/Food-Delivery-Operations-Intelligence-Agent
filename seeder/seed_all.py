"""
Run once to populate all 9 MongoDB collections.
Usage: python seed_all.py
Expects MONGO_URI in environment or .env file at delivery-ops-agent/.env
"""
import os
import sys
import random
import time
from datetime import datetime

from pymongo import MongoClient
from dotenv import load_dotenv

# Load .env from parent directory (delivery-ops-agent/)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/delivery_ops")
client = MongoClient(MONGO_URI)
db = client["delivery_ops"]

ZONES = [
    {"zone_id": "zone_01", "name": "Koramangala",      "lat": 12.9352, "lng": 77.6245},
    {"zone_id": "zone_02", "name": "HSR Layout",        "lat": 12.9116, "lng": 77.6389},
    {"zone_id": "zone_03", "name": "Indiranagar",       "lat": 12.9784, "lng": 77.6408},
    {"zone_id": "zone_04", "name": "BTM Layout",        "lat": 12.9166, "lng": 77.6101},
    {"zone_id": "zone_05", "name": "Whitefield",        "lat": 12.9698, "lng": 77.7499},
    {"zone_id": "zone_06", "name": "Jayanagar",         "lat": 12.9250, "lng": 77.5938},
    {"zone_id": "zone_07", "name": "Marathahalli",      "lat": 12.9591, "lng": 77.6974},
    {"zone_id": "zone_08", "name": "Electronic City",   "lat": 12.8399, "lng": 77.6770},
    {"zone_id": "zone_09", "name": "Bannerghatta Road", "lat": 12.8933, "lng": 77.5975},
    {"zone_id": "zone_10", "name": "Rajajinagar",       "lat": 12.9902, "lng": 77.5560},
    {"zone_id": "zone_11", "name": "Malleshwaram",      "lat": 13.0035, "lng": 77.5673},
    {"zone_id": "zone_12", "name": "Yelahanka",         "lat": 13.1005, "lng": 77.5963},
    {"zone_id": "zone_13", "name": "JP Nagar",          "lat": 12.9063, "lng": 77.5857},
    {"zone_id": "zone_14", "name": "Hebbal",            "lat": 13.0354, "lng": 77.5970},
    {"zone_id": "zone_15", "name": "Sarjapur Road",     "lat": 12.9010, "lng": 77.6850},
    {"zone_id": "zone_16", "name": "Bellandur",         "lat": 12.9261, "lng": 77.6770},
    {"zone_id": "zone_17", "name": "Banashankari",      "lat": 12.9255, "lng": 77.5468},
    {"zone_id": "zone_18", "name": "MG Road",           "lat": 12.9757, "lng": 77.6011},
    {"zone_id": "zone_19", "name": "Cunningham Road",   "lat": 12.9932, "lng": 77.5975},
    {"zone_id": "zone_20", "name": "Kengeri",           "lat": 12.9082, "lng": 77.4824},
]


def seed_city_grid():
    db.city_grid.drop()
    docs = []
    for z in ZONES:
        idle = random.randint(8, 18)
        active = random.randint(2, 8)
        orders = random.randint(4, 14)
        wait = round(random.uniform(8, 22), 1)
        docs.append({
            **z,
            "active_orders": orders,
            "idle_agents": idle,
            "active_agents": active,
            "total_agents": idle + active,
            "avg_wait_minutes": wait,
            "demand_score": round(random.uniform(0.2, 0.6), 2),
            "status": "normal",
            "last_updated": datetime.utcnow().isoformat(),
        })
    db.city_grid.insert_many(docs)
    print(f"  city_grid: {len(docs)} zones")


def seed_zones_baseline():
    db.zones_baseline.drop()
    docs = []
    for z in ZONES:
        docs.append({
            "zone_id": z["zone_id"],
            "baseline_active_orders": random.randint(4, 14),
            "baseline_idle_agents": random.randint(8, 18),
            "baseline_avg_wait_minutes": random.randint(8, 20),
            "recorded_at": datetime.utcnow().isoformat(),
        })
    db.zones_baseline.insert_many(docs)
    print(f"  zones_baseline: {len(docs)} records")


def seed_agents():
    db.agents.drop()
    docs = []
    for i in range(1, 201):
        zone = random.choice(ZONES)
        docs.append({
            "agent_id": f"agent_{i:03d}",
            "current_zone": zone["zone_id"],
            "status": random.choice(["idle", "idle", "idle", "delivering", "returning"]),
            "assigned_order_id": None,
            "last_moved": datetime.utcnow().isoformat(),
        })
    db.agents.insert_many(docs)
    print(f"  agents: {len(docs)}")


def seed_restaurants():
    db.restaurants.drop()
    sys.path.insert(0, os.path.dirname(__file__))
    from seed_restaurants import load_restaurants
    docs = load_restaurants()
    if not docs:
        print("  WARNING: no restaurants loaded from CSV — check ZOMATO CSV path")
        return
    db.restaurants.insert_many(docs)
    print(f"  restaurants: {len(docs)}")


def seed_orders():
    db.orders.drop()
    # Seed a handful of initial unassigned orders per zone
    docs = []
    restaurants = list(db.restaurants.find())
    for z in ZONES:
        zone_rests = [r for r in restaurants if r["zone_id"] == z["zone_id"]]
        if not zone_rests:
            continue
        for _ in range(random.randint(2, 6)):
            docs.append({
                "order_id": f"ord_{int(time.time())}_{random.randint(1000, 9999)}",
                "zone_id": z["zone_id"],
                "restaurant_id": random.choice(zone_rests)["restaurant_id"],
                "assigned_agent_id": None,
                "status": "unassigned",
                "created_at": datetime.utcnow().isoformat(),
                "wait_minutes": random.randint(0, 10),
            })
    db.orders.insert_many(docs)
    print(f"  orders: {len(docs)}")


def seed_action_log():
    db.action_log.drop()
    print("  action_log: empty (ready)")


def seed_agent_notifications():
    db.agent_notifications.drop()
    print("  agent_notifications: empty (ready)")


def seed_demo_triggers():
    db.demo_triggers.drop()
    db.demo_triggers.insert_one({
        "trigger_id": "ipl_spike",
        "description": "IPL match ends near Chinnaswamy — HSR Layout spikes, Koramangala has surplus",
        "mutations": [
            {
                "collection": "city_grid",
                "zone_id": "zone_02",
                "set": {"active_orders": 52, "idle_agents": 3, "avg_wait_minutes": 58, "status": "critical"},
            },
            {
                "collection": "city_grid",
                "zone_id": "zone_01",
                "set": {"idle_agents": 40, "active_orders": 6, "avg_wait_minutes": 8, "status": "normal"},
            },
        ],
    })
    print("  demo_triggers: seeded")


def seed_demo_triggers_full():
    """Extended demo triggers for multiple event scenarios."""
    db.demo_triggers.drop()
    triggers = [
        # ── IPL match post-game spike ──────────────────────────────────────
        {
            "trigger_id": "ipl_spike",
            "description": "IPL match ends at Chinnaswamy — HSR Layout & Indiranagar spike",
            "event_type": "ipl_match",
            "mutations": [
                {"collection": "city_grid", "zone_id": "zone_02",
                 "set": {"active_orders": 52, "idle_agents": 3, "avg_wait_minutes": 58, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_03",
                 "set": {"active_orders": 38, "idle_agents": 4, "avg_wait_minutes": 44, "status": "critical"}},
                # total_agents must be >= idle_agents or simulation math breaks
                {"collection": "city_grid", "zone_id": "zone_01",
                 "set": {"idle_agents": 30, "active_orders": 4, "total_agents": 32, "avg_wait_minutes": 8, "status": "normal"}},
            ],
        },
        # ── Concert at Palace Grounds ──────────────────────────────────────
        {
            "trigger_id": "concert_spike",
            "description": "Concert ends at Palace Grounds — Rajajinagar & Malleshwaram spike",
            "event_type": "concert",
            "mutations": [
                {"collection": "city_grid", "zone_id": "zone_10",
                 "set": {"active_orders": 45, "idle_agents": 2, "avg_wait_minutes": 52, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_11",
                 "set": {"active_orders": 36, "idle_agents": 3, "avg_wait_minutes": 46, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_14",
                 "set": {"idle_agents": 28, "active_orders": 4, "total_agents": 30, "avg_wait_minutes": 7, "status": "normal"}},
            ],
        },
        # ── New Year's Eve / MG Road ───────────────────────────────────────
        {
            "trigger_id": "new_year_spike",
            "description": "New Year's Eve — MG Road, Koramangala, Indiranagar all spike simultaneously",
            "event_type": "new_year_eve",
            "mutations": [
                {"collection": "city_grid", "zone_id": "zone_18",
                 "set": {"active_orders": 60, "idle_agents": 2, "avg_wait_minutes": 65, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_01",
                 "set": {"active_orders": 48, "idle_agents": 3, "avg_wait_minutes": 55, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_03",
                 "set": {"active_orders": 44, "idle_agents": 2, "avg_wait_minutes": 50, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_20",
                 "set": {"idle_agents": 28, "active_orders": 3, "total_agents": 30, "avg_wait_minutes": 6, "status": "normal"}},
                {"collection": "city_grid", "zone_id": "zone_12",
                 "set": {"idle_agents": 25, "active_orders": 4, "total_agents": 27, "avg_wait_minutes": 7, "status": "normal"}},
            ],
        },
        # ── Monsoon first rain ─────────────────────────────────────────────
        {
            "trigger_id": "monsoon_spike",
            "description": "First heavy rain — all residential zones spike as people stay home",
            "event_type": "monsoon_rain",
            "mutations": [
                {"collection": "city_grid", "zone_id": "zone_06",
                 "set": {"active_orders": 40, "idle_agents": 3, "avg_wait_minutes": 48, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_13",
                 "set": {"active_orders": 38, "idle_agents": 2, "avg_wait_minutes": 44, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_17",
                 "set": {"active_orders": 35, "idle_agents": 3, "avg_wait_minutes": 42, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_04",
                 "set": {"active_orders": 34, "idle_agents": 4, "avg_wait_minutes": 40, "status": "critical"}},
                # Yelahanka is unaffected by rain — surplus agents available
                {"collection": "city_grid", "zone_id": "zone_12",
                 "set": {"idle_agents": 26, "active_orders": 3, "total_agents": 28, "avg_wait_minutes": 7, "status": "normal"}},
            ],
        },
        # ── Tech park quarter-end party ────────────────────────────────────
        {
            "trigger_id": "techpark_spike",
            "description": "Quarter-end celebrations in tech corridors — Whitefield & Electronic City spike",
            "event_type": "office_event",
            "mutations": [
                {"collection": "city_grid", "zone_id": "zone_05",
                 "set": {"active_orders": 50, "idle_agents": 2, "avg_wait_minutes": 56, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_08",
                 "set": {"active_orders": 44, "idle_agents": 3, "avg_wait_minutes": 50, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_07",
                 "set": {"idle_agents": 28, "active_orders": 5, "total_agents": 30, "avg_wait_minutes": 8, "status": "normal"}},
            ],
        },
        # ── Diwali night ───────────────────────────────────────────────────
        {
            "trigger_id": "diwali_spike",
            "description": "Diwali night — sweets + snacks orders surge across all residential zones",
            "event_type": "festival_diwali",
            "mutations": [
                {"collection": "city_grid", "zone_id": "zone_06",
                 "set": {"active_orders": 55, "idle_agents": 2, "avg_wait_minutes": 62, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_09",
                 "set": {"active_orders": 48, "idle_agents": 3, "avg_wait_minutes": 54, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_17",
                 "set": {"active_orders": 46, "idle_agents": 2, "avg_wait_minutes": 52, "status": "critical"}},
                {"collection": "city_grid", "zone_id": "zone_12",
                 "set": {"idle_agents": 30, "active_orders": 4, "total_agents": 32, "avg_wait_minutes": 7, "status": "normal"}},
            ],
        },
    ]
    db.demo_triggers.insert_many(triggers)
    print(f"  demo_triggers: {len(triggers)} triggers seeded")


def seed_historical_patterns():
    db.historical_patterns.drop()
    patterns = [
        # ── IPL ────────────────────────────────────────────────────────────
        {
            "pattern_id": "ipl_zone02_postmatch",
            "event_type": "ipl_match",
            "affected_zone": "zone_02",
            "occurrences": 14,
            "avg_demand_spike_percent": 40,
            "avg_resolution_minutes": 14,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 12,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_01", "zone_06"],
            "notes": "Consistently occurs 15-20 min after match end. Redistribution from zone_01 resolves in all 14 cases.",
        },
        {
            "pattern_id": "ipl_zone03_postmatch",
            "event_type": "ipl_match",
            "affected_zone": "zone_03",
            "occurrences": 14,
            "avg_demand_spike_percent": 30,
            "avg_resolution_minutes": 12,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 8,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_18", "zone_19"],
            "notes": "Indiranagar pubs fill up post-match. Zone 18 (MG Road) has surplus during match hours.",
        },
        # ── Concert ────────────────────────────────────────────────────────
        {
            "pattern_id": "concert_zone10_postshow",
            "event_type": "concert",
            "affected_zone": "zone_10",
            "occurrences": 9,
            "avg_demand_spike_percent": 45,
            "avg_resolution_minutes": 18,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 14,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_14", "zone_12"],
            "notes": "Palace Grounds concerts end around 10-11pm. Rajajinagar gets crowd heading home who order late-night food.",
        },
        {
            "pattern_id": "concert_zone11_postshow",
            "event_type": "concert",
            "affected_zone": "zone_11",
            "occurrences": 9,
            "avg_demand_spike_percent": 35,
            "avg_resolution_minutes": 15,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 10,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_14", "zone_19"],
            "notes": "Malleshwaram residential streets see post-concert food orders. Hebbal consistently has surplus.",
        },
        # ── New Year's Eve ─────────────────────────────────────────────────
        {
            "pattern_id": "newyear_zone18",
            "event_type": "new_year_eve",
            "affected_zone": "zone_18",
            "occurrences": 4,
            "avg_demand_spike_percent": 70,
            "avg_resolution_minutes": 25,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 18,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_20", "zone_12"],
            "notes": "MG Road has highest spike of the year. Must pre-position from outer zones (Kengeri, Yelahanka) 2 hours before midnight.",
        },
        {
            "pattern_id": "newyear_zone01",
            "event_type": "new_year_eve",
            "affected_zone": "zone_01",
            "occurrences": 4,
            "avg_demand_spike_percent": 55,
            "avg_resolution_minutes": 20,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 15,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_17", "zone_09"],
            "notes": "Koramangala pubs cause sustained spike from 11pm to 2am. Pre-positioning 2 hrs early prevents critical status.",
        },
        # ── Monsoon ────────────────────────────────────────────────────────
        {
            "pattern_id": "monsoon_zone06",
            "event_type": "monsoon_rain",
            "affected_zone": "zone_06",
            "occurrences": 18,
            "avg_demand_spike_percent": 35,
            "avg_resolution_minutes": 16,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 10,
            "typical_time_of_day": "daytime",
            "source_zones": ["zone_17", "zone_13"],
            "notes": "Rain drives residential demand in Jayanagar. Spike is predictable from weather forecast — pre-position on rain alert.",
        },
        {
            "pattern_id": "monsoon_zone13",
            "event_type": "monsoon_rain",
            "affected_zone": "zone_13",
            "occurrences": 18,
            "avg_demand_spike_percent": 30,
            "avg_resolution_minutes": 14,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 8,
            "typical_time_of_day": "daytime",
            "source_zones": ["zone_09", "zone_06"],
            "notes": "JP Nagar residential spike during rain. Bannerghatta Road usually has surplus (lower restaurant density).",
        },
        # ── Tech park office events ─────────────────────────────────────────
        {
            "pattern_id": "techpark_zone05",
            "event_type": "office_event",
            "affected_zone": "zone_05",
            "occurrences": 12,
            "avg_demand_spike_percent": 50,
            "avg_resolution_minutes": 15,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 14,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_07", "zone_16"],
            "notes": "Whitefield tech parks (RGA Tech, ITPL) drive massive Friday evening spikes on quarter-end. Marathahalli has surplus.",
        },
        {
            "pattern_id": "techpark_zone08",
            "event_type": "office_event",
            "affected_zone": "zone_08",
            "occurrences": 12,
            "avg_demand_spike_percent": 45,
            "avg_resolution_minutes": 14,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 12,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_15", "zone_09"],
            "notes": "Electronic City (Infosys, Wipro campuses) drives spikes on Fridays and quarter-end Thursdays.",
        },
        # ── Festival: Diwali ───────────────────────────────────────────────
        {
            "pattern_id": "diwali_zone06",
            "event_type": "festival_diwali",
            "affected_zone": "zone_06",
            "occurrences": 3,
            "avg_demand_spike_percent": 60,
            "avg_resolution_minutes": 22,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 16,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_13", "zone_17"],
            "notes": "Jayanagar sweets shops overwhelmed on Diwali. Online orders spike 60% as families order mithai + snacks.",
        },
        # ── Regular daily patterns ─────────────────────────────────────────
        {
            "pattern_id": "lunch_zone01_peak",
            "event_type": "lunch_peak",
            "affected_zone": "zone_01",
            "occurrences": 120,
            "avg_demand_spike_percent": 25,
            "avg_resolution_minutes": 10,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 6,
            "typical_time_of_day": "daytime",
            "source_zones": ["zone_06", "zone_04"],
            "notes": "Koramangala tech corridor daily lunch rush 12:30-2pm. Fully predictable — pre-position by 12:15.",
        },
        {
            "pattern_id": "dinner_zone03_peak",
            "event_type": "dinner_peak",
            "affected_zone": "zone_03",
            "occurrences": 90,
            "avg_demand_spike_percent": 30,
            "avg_resolution_minutes": 12,
            "best_action": "agent_redistribution",
            "avg_agents_moved": 8,
            "typical_time_of_day": "evening",
            "source_zones": ["zone_18", "zone_19"],
            "notes": "Indiranagar bar and restaurant strip drives high evening demand. Zone 18 (MG Road) is a reliable source zone.",
        },
    ]
    db.historical_patterns.insert_many(patterns)
    print(f"  historical_patterns: {len(patterns)}")


def seed_scheduled_events():
    db.scheduled_events.drop()
    print("  scheduled_events: empty (ready — use predict_spike.py to create events)")


def seed_manager_goals():
    db.manager_goals.drop()
    print("  manager_goals: empty (ready)")


if __name__ == "__main__":
    print("Seeding delivery_ops database...")
    seed_city_grid()
    seed_zones_baseline()
    seed_agents()
    seed_restaurants()
    seed_orders()
    seed_action_log()
    seed_agent_notifications()
    seed_demo_triggers_full()
    seed_scheduled_events()
    seed_historical_patterns()
    seed_scheduled_events()
    seed_manager_goals()
    print("\nDone. All 10 collections seeded.")
