"""
Demo spike injector — run from a second terminal during the demo.
Usage: python inject_spike.py [trigger_id]
Default trigger_id: ipl_spike
"""
import os
import sys
from datetime import datetime

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/delivery_ops")
client = MongoClient(MONGO_URI)
db = client["delivery_ops"]


def inject(trigger_id: str = "ipl_spike"):
    trigger = db.demo_triggers.find_one({"trigger_id": trigger_id})
    if not trigger:
        print(f"ERROR: trigger '{trigger_id}' not found. Run seed_all.py first.")
        sys.exit(1)

    print(f"Injecting: {trigger['description']}")
    for mutation in trigger["mutations"]:
        result = db[mutation["collection"]].update_one(
            {"zone_id": mutation["zone_id"]},
            {"$set": {**mutation["set"], "last_updated": datetime.utcnow().isoformat()}},
        )
        zone_id = mutation["zone_id"]
        status = mutation["set"].get("status", "?")
        print(f"  {mutation['collection']} / {zone_id} → {status} (matched {result.matched_count})")

    print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] Spike injected.")
    print("Agent will detect within 60 seconds and post an approval card.")


if __name__ == "__main__":
    trigger_id = sys.argv[1] if len(sys.argv) > 1 else "ipl_spike"
    inject(trigger_id)
