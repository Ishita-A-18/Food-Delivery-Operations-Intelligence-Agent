"""
Simulation tick — run alongside the backend.
Generates Poisson-distributed orders every 60 seconds and recomputes zone metrics.
Usage: python simulation_tick.py
"""
import os
import sys
import time
import random
import numpy as np
from datetime import datetime

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/delivery_ops")
client = MongoClient(MONGO_URI)
db = client["delivery_ops"]

# Orders per zone per minute at base rate (Poisson lambda)
BASE_ORDER_RATE = 2.5

TIME_MULTIPLIERS = {
    range(7, 10):  1.2,  # breakfast
    range(12, 14): 1.8,  # lunch peak
    range(18, 22): 2.1,  # dinner peak
    range(22, 24): 0.6,  # late night
}


def get_multiplier() -> float:
    hour = datetime.utcnow().hour
    for time_range, mult in TIME_MULTIPLIERS.items():
        if hour in time_range:
            return mult
    return 0.8


def tick():
    multiplier = get_multiplier()
    zones = list(db.city_grid.find())

    for zone in zones:
        zone_id = zone["zone_id"]

        # Age all unassigned orders in this zone by 1 minute
        db.orders.update_many(
            {"zone_id": zone_id, "status": "unassigned"},
            {"$inc": {"wait_minutes": 1}},
        )

        # Occasionally assign old orders to idle agents (simulate delivery pickup)
        old_orders = list(
            db.orders.find({"zone_id": zone_id, "status": "unassigned", "wait_minutes": {"$gt": 8}})
            .limit(3)
        )
        for order in old_orders:
            agent = db.agents.find_one({"current_zone": zone_id, "status": "idle"})
            if agent:
                db.agents.update_one(
                    {"agent_id": agent["agent_id"]},
                    {"$set": {"status": "delivering", "assigned_order_id": order["order_id"]}},
                )
                db.orders.update_one(
                    {"order_id": order["order_id"]},
                    {"$set": {"status": "assigned", "assigned_agent_id": agent["agent_id"]}},
                )

        # Occasionally return delivering agents to idle
        delivering = list(
            db.agents.find({"current_zone": zone_id, "status": "delivering"}).limit(2)
        )
        for agent in delivering:
            if random.random() < 0.4:  # 40% chance each tick
                db.agents.update_one(
                    {"agent_id": agent["agent_id"]},
                    {"$set": {"status": "idle", "assigned_order_id": None}},
                )

        # Generate new orders via Poisson distribution
        new_order_count = int(np.random.poisson(lam=BASE_ORDER_RATE * multiplier))
        restaurants = list(db.restaurants.find({"zone_id": zone_id, "status": "open"}))
        if restaurants:
            for _ in range(new_order_count):
                db.orders.insert_one({
                    "order_id": f"ord_{int(time.time())}_{random.randint(1000, 9999)}",
                    "zone_id": zone_id,
                    "restaurant_id": random.choice(restaurants)["restaurant_id"],
                    "assigned_agent_id": None,
                    "status": "unassigned",
                    "created_at": datetime.utcnow().isoformat(),
                    "wait_minutes": 0,
                })

        # Recompute zone metrics
        unassigned = list(db.orders.find({"zone_id": zone_id, "status": "unassigned"}))
        avg_wait = (
            sum(o["wait_minutes"] for o in unassigned) / len(unassigned)
            if unassigned else 0
        )
        idle_count = db.agents.count_documents({"current_zone": zone_id, "status": "idle"})
        active_count = db.agents.count_documents({"current_zone": zone_id, "status": "delivering"})
        shortage = len(unassigned) - idle_count

        if avg_wait > 35 and shortage > 5:
            status = "critical"
        elif avg_wait > 25 or shortage > 2:
            status = "watch"
        else:
            status = "normal"

        db.city_grid.update_one(
            {"zone_id": zone_id},
            {"$set": {
                "active_orders": len(unassigned),
                "idle_agents": idle_count,
                "active_agents": active_count,
                "avg_wait_minutes": round(avg_wait, 1),
                "demand_score": round(min(1.0, len(unassigned) / max(1, idle_count + active_count)), 2),
                "status": status,
                "last_updated": datetime.utcnow().isoformat(),
            }},
        )

    print(f"[tick] {datetime.utcnow().strftime('%H:%M:%S')} — multiplier {multiplier:.1f}x", flush=True)


if __name__ == "__main__":
    print("Simulation tick running. Ctrl+C to stop.")
    while True:
        try:
            tick()
        except Exception as exc:
            print(f"[tick] error: {exc}", flush=True)
        time.sleep(60)
