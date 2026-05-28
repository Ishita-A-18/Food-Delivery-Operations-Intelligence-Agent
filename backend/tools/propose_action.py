from uuid import uuid4
from datetime import datetime


def _build_recommendation(moves: list, zone_name: str) -> str:
    if not moves:
        return f"Investigate {zone_name}"
    agent_moves = [m for m in moves if m.get("type") == "move_agent"]
    pauses = [m for m in moves if m.get("type") == "pause_restaurant"]
    parts = []
    if agent_moves:
        from_zone = agent_moves[0].get("from_zone", "nearby zone")
        parts.append(f"Move {len(agent_moves)} agents from {from_zone} to {zone_name}")
    if pauses:
        parts.append(f"pause {len(pauses)} restaurant(s)")
    return " + ".join(parts) if parts else f"Take action in {zone_name}"


def propose_action(db, anomaly: dict, reasoning: str, proposed_moves: list) -> str:
    """Write a pending recommendation to MongoDB. Returns the new action_id."""
    zone = anomaly["zone"]
    action = {
        "action_id": f"act_{uuid4().hex[:6]}",
        "type": "agent_redistribution",
        "status": "pending",
        "trigger_zone": zone["zone_id"],
        "recommendation": _build_recommendation(proposed_moves, zone["name"]),
        "reasoning": reasoning,
        "proposed_actions": proposed_moves,
        "created_at": datetime.utcnow().isoformat(),
        "approved_at": None,
        "approved_by": None,
        "modification": None,
        "executed_at": None,
        "outcome": None,
    }
    db.action_log.insert_one(action)
    return action["action_id"]
