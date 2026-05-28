"""
Gemini-powered decision engine.

Architecture:
  MongoDB Atlas  <-->  MCP Server (/mcp/sse)  <-- external MCP clients
       ^
       |  (same tool functions, called directly)
       v
  Gemini (function calling)  <-->  gemini_agent.py

The MCP server (mcp_server.py) exposes the same MongoDB tools via the
Model Context Protocol for external clients. Internally, Gemini calls
the tool functions directly to avoid a circular HTTP dependency.
"""
import json
import os
from datetime import datetime, timedelta
from uuid import uuid4

from google import genai
from google.genai import types

SYSTEM_PROMPT = """
You are an AI operations manager for QuickBite, a food delivery platform serving Bangalore, India.

You monitor 20 delivery zones in real time and propose agent redistributions for human approval.
You NEVER execute actions directly — you only propose. A human manager approves or rejects every action.

Zone reference (zone_id → neighbourhood):
zone_01=Koramangala, zone_02=HSR Layout, zone_03=Indiranagar, zone_04=BTM Layout,
zone_05=Whitefield, zone_06=Jayanagar, zone_07=Marathahalli, zone_08=Electronic City,
zone_09=Bannerghatta Road, zone_10=Rajajinagar, zone_11=Malleshwaram, zone_12=Yelahanka,
zone_13=JP Nagar, zone_14=Hebbal, zone_15=Sarjapur Road, zone_16=Bellandur,
zone_17=Banashankari, zone_18=MG Road, zone_19=Cunningham Road, zone_20=Kengeri

Your decision process each cycle:
1. Call get_city_state — see the live MongoDB Atlas data
2. Call get_upcoming_events — check for predicted spikes to handle proactively
3. For critical zones, call query_historical_patterns — reference past data
4. Call get_surplus_zones — find where to pull agents from
5. Call propose_action — submit recommendation (max 2 per cycle)

Rules:
- Only act on zones where avg_wait > 35 min AND agent shortage > 5
- Write reasoning a human manager can read and act on in 10 seconds
- For upcoming events use action_type "preemptive_redistribution"
- For current critical zones use action_type "agent_redistribution"
- If a manager goal is included, address it specifically
"""


def run_gemini_cycle(db, anomalies: list, manager_goal: str = None) -> bool:
    """Entry point from agent_loop (sync thread). Returns True if Gemini succeeded."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("[gemini] GEMINI_API_KEY not set — using fallback", flush=True)
        return False

    pending_docs = list(db.action_log.find({"status": "pending"}, {"trigger_zone": 1}))
    pending_zone_ids = {d.get("trigger_zone") for d in pending_docs if d.get("trigger_zone")}

    city_context = _build_city_context(db, anomalies, pending_zone_ids)
    if not city_context and not manager_goal:
        return True  # nothing to do, not a failure

    prompt_parts = []
    if manager_goal:
        prompt_parts.append(f"MANAGER ESCALATION: \"{manager_goal}\"\n")
    prompt_parts.append(city_context)
    prompt = "\n".join(prompt_parts)

    proposals_made = [0]

    # ── Tool functions (same logic as mcp_server.py, called directly) ─────────

    def get_city_state() -> str:
        """Read live state of all 20 Bangalore delivery zones from MongoDB Atlas."""
        zones = list(db.city_grid.find({}, {"_id": 0}))
        for z in zones:
            z["agent_shortage"] = z["active_orders"] - z["idle_agents"]
            z["is_critical"] = z["avg_wait_minutes"] > 35 and z["agent_shortage"] > 5
        return json.dumps(zones)

    def get_upcoming_events() -> str:
        """Check MongoDB Atlas for events in the next 90 minutes that may cause spikes."""
        cutoff = (datetime.utcnow() + timedelta(minutes=90)).isoformat()
        events = list(db.scheduled_events.find(
            {"status": "upcoming", "scheduled_time": {"$lte": cutoff}},
            {"_id": 0},
        ))
        return json.dumps({"events": events})

    def query_historical_patterns(zone_id: str, event_type: str = "") -> str:
        """Look up historical demand spike patterns from MongoDB Atlas for a zone.

        Args:
            zone_id: Zone identifier e.g. zone_02
            event_type: Optional — ipl_match, concert, monsoon_rain,
                        festival_diwali, office_event, new_year_eve
        """
        query = {"affected_zone": zone_id}
        if event_type:
            query["event_type"] = event_type
        pattern = db.historical_patterns.find_one(query, {"_id": 0})
        if not pattern:
            pattern = db.historical_patterns.find_one({"affected_zone": zone_id}, {"_id": 0})
        if not pattern:
            return json.dumps({"found": False})
        return json.dumps({"found": True, **pattern})

    def get_surplus_zones() -> str:
        """Find zones in MongoDB Atlas with surplus idle agents available for redistribution."""
        zones = list(db.city_grid.find({}, {"_id": 0}))
        surplus = [
            z for z in zones
            if z["idle_agents"] > z["active_orders"] * 1.5 and z["idle_agents"] > 6
        ]
        surplus.sort(key=lambda z: z["idle_agents"], reverse=True)
        return json.dumps(surplus[:5])

    def propose_action(
        zone_id: str,
        source_zone_id: str,
        agents_to_move: int,
        recommendation: str,
        reasoning: str,
        action_type: str = "agent_redistribution",
    ) -> str:
        """Write a pending redistribution proposal to MongoDB Atlas for human approval.

        Args:
            zone_id: Destination zone that needs agents
            source_zone_id: Source zone with surplus idle agents
            agents_to_move: Number of agents to move (5-15)
            recommendation: One-line summary for the approval card title
            reasoning: 2-4 sentence reasoning for the human manager
            action_type: agent_redistribution or preemptive_redistribution
        """
        if zone_id in pending_zone_ids:
            return json.dumps({"status": "skipped", "reason": "already pending"})
        if proposals_made[0] >= 2:
            return json.dumps({"status": "skipped", "reason": "max 2 per cycle"})

        agents = list(db.agents.aggregate([
            {"$match": {"current_zone": source_zone_id, "status": "idle"}},
            {"$sample": {"size": min(int(agents_to_move), 20)}},
        ]))
        if not agents:
            return json.dumps({"status": "skipped", "reason": f"no idle agents in {source_zone_id}"})

        moves = [
            {"type": "move_agent", "agent_id": a["agent_id"],
             "from_zone": source_zone_id, "to_zone": zone_id}
            for a in agents
        ]
        action = {
            "action_id":        f"act_{uuid4().hex[:6]}",
            "type":             action_type,
            "status":           "pending",
            "trigger_zone":     zone_id,
            "zone_id":          zone_id,
            "recommendation":   recommendation,
            "reasoning":        reasoning,
            "proposed_actions": moves,
            "created_at":       datetime.utcnow().isoformat(),
            "approved_at":      None,
            "approved_by":      None,
            "modification":     None,
            "executed_at":      None,
            "outcome":          None,
        }
        db.action_log.insert_one(action)
        pending_zone_ids.add(zone_id)
        proposals_made[0] += 1
        print(f"[gemini] proposed {action['action_id']} ({action_type}) → {zone_id}", flush=True)
        return json.dumps({"status": "proposed", "action_id": action["action_id"]})

    # ── Call Gemini with automatic function calling ────────────────────────────
    try:
        client = genai.Client(api_key=api_key)
        chat = client.chats.create(
            model="gemini-2.0-flash-lite",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[
                    get_city_state,
                    get_upcoming_events,
                    query_historical_patterns,
                    get_surplus_zones,
                    propose_action,
                ],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=False,
                    maximum_remote_calls=10,
                ),
            ),
        )
        response = chat.send_message(prompt)
        if response.text:
            print(f"[gemini] {response.text[:300]}", flush=True)
        return True
    except Exception as exc:
        print(f"[gemini] error: {exc}", flush=True)
        return False


def _build_city_context(db, anomalies: list, pending_zone_ids: set) -> str:
    actionable = [a for a in anomalies if a["zone"]["zone_id"] not in pending_zone_ids]

    if not actionable:
        cutoff = (datetime.utcnow() + timedelta(minutes=90)).isoformat()
        has_upcoming = db.scheduled_events.count_documents(
            {"status": "upcoming", "scheduled_time": {"$lte": cutoff}}
        )
        if not has_upcoming:
            return ""

    lines = [f"Time: {datetime.utcnow().strftime('%H:%M UTC')} — Bangalore delivery network\n"]

    if actionable:
        lines.append("ZONES NEEDING ATTENTION:")
        for a in actionable[:5]:
            z = a["zone"]
            lines.append(
                f"  • {z['name']} ({z['zone_id']}): {z['active_orders']} orders, "
                f"{z['idle_agents']} idle agents, wait={z['avg_wait_minutes']}min, "
                f"shortage={a['agent_shortage']}"
            )
    else:
        lines.append("No critical zones — check upcoming events.")

    lines.append(
        "\nUse the tools to get full city state, check upcoming events, "
        "query historical patterns, and propose actions."
    )
    return "\n".join(lines)
