from uuid import uuid4
from datetime import datetime


def execute_action(db, action_id: str) -> None:
    """Apply approved mutations. Hard-stops if status is not 'approved'."""
    action = db.action_log.find_one({"action_id": action_id})
    if not action:
        raise ValueError(f"Action {action_id} not found")

    if action["status"] != "approved":
        raise PermissionError(
            f"Cannot execute action {action_id} — status is '{action['status']}'"
        )

    zone_deltas: dict[str, int] = {}  # zone_id → idle_agents delta

    for move in action.get("proposed_actions", []):
        if move["type"] == "move_agent":
            db.agents.update_one(
                {"agent_id": move["agent_id"]},
                {"$set": {
                    "current_zone": move["to_zone"],
                    "last_moved": datetime.utcnow().isoformat(),
                }},
            )

            zone_deltas[move["from_zone"]] = zone_deltas.get(move["from_zone"], 0) - 1
            zone_deltas[move["to_zone"]]   = zone_deltas.get(move["to_zone"],   0) + 1

            dest_zone = db.city_grid.find_one({"zone_id": move["to_zone"]})
            zone_name = dest_zone["name"] if dest_zone else move["to_zone"]

            db.agent_notifications.insert_one({
                "notification_id": f"notif_{uuid4().hex[:6]}",
                "agent_id": move["agent_id"],
                "action_id": action_id,
                "message": f"New zone assigned: Move to {zone_name}. Orders waiting.",
                "status": "sent",
                "sent_at": datetime.utcnow().isoformat(),
                "acknowledged_at": None,
            })

        elif move["type"] == "pause_restaurant":
            db.restaurants.update_one(
                {"restaurant_id": move["restaurant_id"]},
                {"$set": {
                    "status": "paused",
                    "paused_at": datetime.utcnow().isoformat(),
                }},
            )

    # Update city_grid and record before/after for each zone
    zone_changes = []
    for zone_id, delta in zone_deltas.items():
        zone = db.city_grid.find_one({"zone_id": zone_id})
        if not zone:
            continue
        idle_before = zone["idle_agents"]
        new_idle    = max(0, idle_before + delta)
        new_total   = max(new_idle, zone["total_agents"] + delta)
        unserved    = max(0, zone["active_orders"] - (new_total - new_idle))
        wait        = round(min(max(8.0 + unserved * 2.5, 4.0), 90.0), 1)
        shortage    = zone["active_orders"] - new_idle
        if wait > 35 and shortage > 5:
            status = "critical"
        elif wait > 22:
            status = "watch"
        else:
            status = "normal"
        db.city_grid.update_one(
            {"zone_id": zone_id},
            {"$set": {
                "idle_agents":      new_idle,
                "total_agents":     new_total,
                "avg_wait_minutes": wait,
                "status":           status,
                "last_updated":     datetime.utcnow().isoformat(),
            }},
        )
        zone_changes.append({
            "zone_id":      zone_id,
            "idle_before":  idle_before,
            "idle_after":   new_idle,
            "delta":        delta,
        })

    db.action_log.update_one(
        {"action_id": action_id},
        {"$set": {
            "status": "executed",
            "executed_at": datetime.utcnow().isoformat(),
            "zone_changes": zone_changes,
        }},
    )

    # Zones remain locked after execution — only another redistribution action can change them
