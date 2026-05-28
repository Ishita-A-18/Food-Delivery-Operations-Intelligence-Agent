import time
import sys
import os
from datetime import datetime, timedelta
from uuid import uuid4

sys.path.insert(0, os.path.dirname(__file__))

from db import get_db
from tools.read_city_state import read_city_state
from tools.execute_action import execute_action
from tools.close_incident import close_incident
from gemini_agent import run_gemini_cycle


def agent_loop() -> None:
    """
    Main ops loop — runs every 60s in a background thread.

    Each cycle:
      1. Read live city state
      2. Hand anomalies + upcoming events to Gemini → it proposes actions
      3. Process any manager goals through Gemini
      4. Execute actions that the human has approved
    """
    db = get_db()
    print("[agent_loop] started (Gemini-powered)", flush=True)

    while True:
        try:
            # ── STEP 1: read city state ───────────────────────────────────────
            anomalies = read_city_state(db)

            # ── STEP 2: Gemini decides — reactive anomalies + proactive events ─
            gemini_ok = run_gemini_cycle(db, anomalies)
            if not gemini_ok:
                _fallback_propose(db, anomalies)

            # ── STEP 3: manager goals (ad-hoc natural language) ───────────────
            pending_goal = db.manager_goals.find_one({"status": "pending"})
            if pending_goal:
                goal_text = pending_goal.get("goal", "")
                ok = run_gemini_cycle(db, anomalies, manager_goal=goal_text)
                if not ok:
                    _fallback_goal(db, goal_text)
                db.manager_goals.update_one(
                    {"_id": pending_goal["_id"]},
                    {"$set": {"status": "processed"}},
                )
                print(f"[agent_loop] manager goal processed: {goal_text[:60]}", flush=True)

            # ── STEP 4: execute approved actions ─────────────────────────────
            approved = list(db.action_log.find({"status": "approved"}))
            for action in approved:
                try:
                    execute_action(db, action["action_id"])
                    print(f"[agent_loop] executed {action['action_id']}", flush=True)
                except Exception as exc:
                    print(f"[agent_loop] execute error {action['action_id']}: {exc}", flush=True)

            # ── STEP 5: close resolved incidents ─────────────────────────────
            executed = list(db.action_log.find({"status": "executed"}))
            for action in executed:
                try:
                    close_incident(db, action["action_id"])
                except Exception as exc:
                    print(f"[agent_loop] close error {action['action_id']}: {exc}", flush=True)

        except Exception as exc:
            print(f"[agent_loop] error: {exc}", flush=True)

        time.sleep(60)


def _fallback_goal(db, goal_text: str) -> None:
    """Fallback handler for manager chat goals when Gemini is unavailable."""
    goal_lower = goal_text.lower()

    # Try to find a zone mentioned by name in the goal
    zones = list(db.city_grid.find())
    target_zone = None
    for z in zones:
        if z["name"].lower() in goal_lower:
            target_zone = z
            break

    # Fall back to worst zone by wait time
    if not target_zone:
        zones_sorted = sorted(zones, key=lambda z: z["avg_wait_minutes"], reverse=True)
        # Skip zones that already have a pending action
        pending = {d.get("trigger_zone") for d in db.action_log.find({"status": "pending"}, {"trigger_zone": 1})}
        target_zone = next((z for z in zones_sorted if z["zone_id"] not in pending), zones_sorted[0])

    if not target_zone:
        return

    zone_id = target_zone["zone_id"]
    existing = db.action_log.find_one({"trigger_zone": zone_id, "status": "pending"})
    if existing:
        return

    # Find best source zone
    all_zones = list(db.city_grid.find())
    sources = sorted(
        [z for z in all_zones if z["idle_agents"] > 5 and z["zone_id"] != zone_id],
        key=lambda z: z["idle_agents"], reverse=True
    )
    if not sources:
        return

    source = sources[0]
    agents = list(db.agents.aggregate([
        {"$match": {"current_zone": source["zone_id"], "status": "idle"}},
        {"$sample": {"size": 5}},
    ]))
    if not agents:
        return

    moves = [{"type": "move_agent", "agent_id": a["agent_id"],
              "from_zone": source["zone_id"], "to_zone": zone_id} for a in agents]

    action = {
        "action_id":        f"act_{uuid4().hex[:6]}",
        "type":             "agent_redistribution",
        "status":           "pending",
        "trigger_zone":     zone_id,
        "zone_id":          zone_id,
        "recommendation":   f"Move {len(moves)} agents from {source['name']} to {target_zone['name']}",
        "reasoning":        (
            f"Manager escalation: \"{goal_text}\". "
            f"{target_zone['name']} currently has {target_zone['active_orders']} active orders "
            f"with {target_zone['idle_agents']} idle agents (avg wait {target_zone['avg_wait_minutes']} min). "
            f"Proposing to move {len(moves)} agents from {source['name']} which has {source['idle_agents']} idle."
        ),
        "proposed_actions": moves,
        "created_at":       datetime.utcnow().isoformat(),
        "approved_at": None, "approved_by": None,
        "modification": None, "executed_at": None, "outcome": None,
    }
    db.action_log.insert_one(action)
    print(f"[fallback] goal → proposed {action['action_id']} for {zone_id}", flush=True)


def _fallback_propose(db, anomalies: list) -> None:
    """Rule-based fallback when Gemini API is unavailable."""
    pending_docs = list(db.action_log.find({"status": "pending"}, {"trigger_zone": 1}))
    pending_zone_ids = {d.get("trigger_zone") for d in pending_docs if d.get("trigger_zone")}
    proposed = 0

    for anomaly in anomalies[:2]:
        if proposed >= 2:
            break
        zone = anomaly["zone"]
        zone_id = zone["zone_id"]
        if zone_id in pending_zone_ids:
            continue
        if not anomaly["candidate_sources"]:
            continue

        source = anomaly["candidate_sources"][0]
        n = min(anomaly["agent_shortage"], 11)
        agents = list(db.agents.aggregate([
            {"$match": {"current_zone": source["zone_id"], "status": "idle"}},
            {"$sample": {"size": n}},
        ]))
        if not agents:
            continue

        moves = [{"type": "move_agent", "agent_id": a["agent_id"],
                  "from_zone": source["zone_id"], "to_zone": zone_id} for a in agents]

        # Check historical pattern for richer reasoning
        pattern = db.historical_patterns.find_one({"affected_zone": zone_id})
        if pattern:
            reasoning = (
                f"{zone['name']} has {zone['active_orders']} active orders with "
                f"{zone['idle_agents']} idle agents (avg wait {zone['avg_wait_minutes']} min). "
                f"Historical data ({pattern['occurrences']} past occurrences): "
                f"avg resolution {pattern['avg_resolution_minutes']} min via redistribution. "
                f"{pattern.get('notes', '')}"
            )
        else:
            reasoning = (
                f"{zone['name']} has {zone['active_orders']} active orders with only "
                f"{zone['idle_agents']} idle agents (avg wait {zone['avg_wait_minutes']} min). "
                f"Agent shortage: {anomaly['agent_shortage']}. "
                f"Proposing standard redistribution from {source['name']}."
            )

        action = {
            "action_id":        f"act_{uuid4().hex[:6]}",
            "type":             "agent_redistribution",
            "status":           "pending",
            "trigger_zone":     zone_id,
            "zone_id":          zone_id,
            "recommendation":   f"Move {len(moves)} agents from {source['name']} to {zone['name']}",
            "reasoning":        reasoning,
            "proposed_actions": moves,
            "created_at":       datetime.utcnow().isoformat(),
            "approved_at": None, "approved_by": None,
            "modification": None, "executed_at": None, "outcome": None,
        }
        db.action_log.insert_one(action)
        pending_zone_ids.add(zone_id)
        proposed += 1
        print(f"[fallback] proposed {action['action_id']} for {zone_id}", flush=True)

    # Proactive fallback: check upcoming events
    if proposed < 2:
        _fallback_proactive(db, pending_zone_ids, proposed)


def _fallback_proactive(db, pending_zone_ids: set, already_proposed: int) -> None:
    cutoff = (datetime.utcnow() + timedelta(minutes=90)).isoformat()
    events = list(db.scheduled_events.find(
        {"status": "upcoming", "scheduled_time": {"$lte": cutoff}}
    ))
    proposed = already_proposed
    for event in events:
        if proposed >= 2:
            break
        for zone_id in event.get("affected_zones", []):
            if zone_id in pending_zone_ids or proposed >= 2:
                continue
            pattern = db.historical_patterns.find_one(
                {"affected_zone": zone_id, "event_type": event["event_type"]}
            )
            if not pattern:
                continue
            zone = db.city_grid.find_one({"zone_id": zone_id})
            all_zones = list(db.city_grid.find())
            sources = sorted(
                [z for z in all_zones if z["idle_agents"] > z["active_orders"] * 1.2 and z["zone_id"] != zone_id],
                key=lambda z: z["idle_agents"], reverse=True
            )
            if not sources or not zone:
                continue
            source = sources[0]
            n = pattern.get("avg_agents_moved", 8)
            agents = list(db.agents.aggregate([
                {"$match": {"current_zone": source["zone_id"], "status": "idle"}},
                {"$sample": {"size": n}},
            ]))
            if not agents:
                continue
            moves = [{"type": "move_agent", "agent_id": a["agent_id"],
                      "from_zone": source["zone_id"], "to_zone": zone_id} for a in agents]
            scheduled_dt = datetime.fromisoformat(event["scheduled_time"])
            minutes_until = max(1, int((scheduled_dt - datetime.utcnow()).total_seconds() / 60))
            action = {
                "action_id":        f"act_{uuid4().hex[:6]}",
                "type":             "preemptive_redistribution",
                "status":           "pending",
                "trigger_zone":     zone_id,
                "zone_id":          zone_id,
                "recommendation":   f"Pre-position {len(moves)} agents in {zone['name']} before {event['name']}",
                "reasoning":        (
                    f"PROACTIVE — {event['name']} starts in {minutes_until} min. "
                    f"Historical data ({pattern['occurrences']} occurrences): "
                    f"{zone['name']} spikes {pattern['avg_demand_spike_percent']}%, "
                    f"resolved in {pattern['avg_resolution_minutes']} min via redistribution. "
                    f"{pattern.get('notes', '')}"
                ),
                "proposed_actions": moves,
                "created_at":       datetime.utcnow().isoformat(),
                "approved_at": None, "approved_by": None,
                "modification": None, "executed_at": None, "outcome": None,
            }
            db.action_log.insert_one(action)
            db.scheduled_events.update_one(
                {"event_id": event["event_id"]}, {"$set": {"status": "acknowledged"}}
            )
            pending_zone_ids.add(zone_id)
            proposed += 1
            print(f"[fallback] PROACTIVE {action['action_id']} for {zone_id} ({event['name']})", flush=True)
