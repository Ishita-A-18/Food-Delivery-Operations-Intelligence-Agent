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

    for move in action.get("proposed_actions", []):
        if move["type"] == "move_agent":
            db.agents.update_one(
                {"agent_id": move["agent_id"]},
                {"$set": {
                    "current_zone": move["to_zone"],
                    "last_moved": datetime.utcnow().isoformat(),
                }},
            )

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

    db.action_log.update_one(
        {"action_id": action_id},
        {"$set": {
            "status": "executed",
            "executed_at": datetime.utcnow().isoformat(),
        }},
    )
