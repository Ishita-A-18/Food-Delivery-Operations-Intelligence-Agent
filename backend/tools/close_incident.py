from datetime import datetime


def close_incident(db, action_id: str) -> bool:
    """Check if the affected zone has normalised; if so, log the outcome and resolve."""
    action = db.action_log.find_one({"action_id": action_id})
    if not action:
        return False

    zone = db.city_grid.find_one({"zone_id": action["trigger_zone"]})
    baseline = db.zones_baseline.find_one({"zone_id": action["trigger_zone"]})

    if not zone or not baseline:
        return False

    normalized = (
        zone["avg_wait_minutes"] <= baseline["baseline_avg_wait_minutes"] * 1.2
        and zone["idle_agents"] >= baseline["baseline_idle_agents"] * 0.8
    )

    if normalized:
        created = datetime.fromisoformat(action["created_at"])
        resolved = datetime.utcnow()
        resolution_minutes = max(1, (resolved - created).seconds // 60)
        customer_minutes_saved = resolution_minutes * zone.get("active_orders", 0)

        db.action_log.update_one(
            {"action_id": action_id},
            {"$set": {
                "status": "resolved",
                "outcome": {
                    "resolution_minutes": resolution_minutes,
                    "customer_minutes_saved": customer_minutes_saved,
                    "final_wait_minutes": zone["avg_wait_minutes"],
                },
            }},
        )
        return True

    return False
