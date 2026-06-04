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
4. Call get_nearby_surplus_zones(zone_id) — find geographically close zones (within 8 km) with idle agents
5. Call propose_action — submit recommendation (max 2 per cycle)

Rules:
- For autonomous monitoring: only act on zones where avg_wait > 35 min AND agent shortage > 5
- For MANAGER ESCALATION: address the goal directly regardless of thresholds — the manager sees something you don't. Find the zone they mention, check its state, and propose a redistribution even if wait times look acceptable. Use action_type "agent_redistribution".
- PROXIMITY RULE: Only source agents from zones within 8 km of the target. Agents cannot travel across the city. Use get_nearby_surplus_zones to find valid sources.
- MULTI-SOURCE RULE: Never drain a single zone. Split the needed agents across 2–3 nearby source zones. Pass all source zone IDs comma-separated in source_zone_ids e.g. "zone_02,zone_04,zone_06".
- Write reasoning a human manager can read and act on in 10 seconds — include which zones agents come from and why
- For upcoming events use action_type "preemptive_redistribution"
- Always call propose_action if there is a MANAGER ESCALATION, unless there are genuinely zero idle agents anywhere
"""


def run_gemini_cycle(db, anomalies: list, manager_goal: str = None) -> bool:
    """Entry point from agent_loop (sync thread). Returns True if Gemini succeeded."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("[gemini] GEMINI_API_KEY not set — using fallback", flush=True)
        return False

    pending_docs = list(db.action_log.find({"status": "pending"}, {"trigger_zone": 1}))
    pending_zone_ids = {d.get("trigger_zone") for d in pending_docs if d.get("trigger_zone")}

    city_context = _build_city_context(db, anomalies, pending_zone_ids, force=bool(manager_goal))
    if not city_context and not manager_goal:
        return True  # nothing to do, not a failure

    prompt_parts = []
    if manager_goal:
        prompt_parts.append(f"MANAGER ESCALATION: \"{manager_goal}\"\nAddress this goal directly. Call get_city_state to find the zone, then propose a redistribution.\n")
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

    def get_nearby_surplus_zones(zone_id: str) -> str:
        """Find zones within 8 km of the target that have surplus idle agents.
        Always call this before propose_action to ensure sources are geographically realistic.

        Args:
            zone_id: The destination zone that needs agents
        """
        from zone_distances import nearby_surplus_zones
        all_zones = list(db.city_grid.find({}, {"_id": 0}))
        nearby = nearby_surplus_zones(zone_id, all_zones)
        result = [
            {
                "zone_id": z["zone_id"],
                "name": z["name"],
                "idle_agents": z["idle_agents"],
                "active_orders": z["active_orders"],
                "distance_km": round(dist, 1),
            }
            for dist, z in nearby[:5]
        ]
        return json.dumps(result)

    def propose_action(
        zone_id: str,
        source_zone_ids: str,
        agents_to_move: int,
        recommendation: str,
        reasoning: str,
        action_type: str = "agent_redistribution",
    ) -> str:
        """Write a pending redistribution proposal to MongoDB Atlas for human approval.

        Args:
            zone_id: Destination zone that needs agents
            source_zone_ids: Comma-separated source zone IDs within 8 km e.g. "zone_02,zone_04"
            agents_to_move: Total number of agents to move (5-15)
            recommendation: One-line summary for the approval card title
            reasoning: 2-4 sentence reasoning for the human manager
            action_type: agent_redistribution or preemptive_redistribution
        """
        if zone_id in pending_zone_ids:
            return json.dumps({"status": "skipped", "reason": "already pending"})
        if proposals_made[0] >= 2:
            return json.dumps({"status": "skipped", "reason": "max 2 per cycle"})

        source_ids = [s.strip() for s in source_zone_ids.split(",") if s.strip()]
        if not source_ids:
            return json.dumps({"status": "skipped", "reason": "no source zones provided"})

        all_zones = list(db.city_grid.find({}, {"_id": 0}))
        zone_map = {z["zone_id"]: z for z in all_zones}

        sources_with_surplus = []
        for sid in source_ids[:3]:
            z = zone_map.get(sid)
            if not z:
                continue
            surplus = max(0, z["idle_agents"] - max(2, int(z.get("active_orders", 0) * 0.4)))
            if surplus > 0:
                sources_with_surplus.append((z, surplus))

        if not sources_with_surplus:
            return json.dumps({"status": "skipped", "reason": "no idle agents in specified source zones"})

        total_surplus = sum(s for _, s in sources_with_surplus)
        moves = []
        remaining = min(int(agents_to_move), 20)

        for source_zone, surplus in sources_with_surplus:
            if remaining <= 0:
                break
            take = max(1, min(round(agents_to_move * surplus / total_surplus), surplus, remaining))
            agents = list(db.agents.aggregate([
                {"$match": {"current_zone": source_zone["zone_id"], "status": "idle"}},
                {"$sample": {"size": take}},
            ]))
            for a in agents:
                moves.append({
                    "type": "move_agent",
                    "agent_id": a["agent_id"],
                    "from_zone": source_zone["zone_id"],
                    "to_zone": zone_id,
                })
            remaining -= len(agents)

        if not moves:
            return json.dumps({"status": "skipped", "reason": "could not sample agents from source zones"})

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

        # Lock target + source zones so simulation skips them while action is pending
        lock_ids = {zone_id} | {m["from_zone"] for m in moves}
        db.city_grid.update_many(
            {"zone_id": {"$in": list(lock_ids)}},
            {"$set": {"locked": True}},
        )

        print(f"[gemini] proposed {action['action_id']} ({action_type}) → {zone_id} from [{source_zone_ids}]", flush=True)
        return json.dumps({"status": "proposed", "action_id": action["action_id"]})

    # ── Call Gemini with automatic function calling ────────────────────────────
    try:
        client = genai.Client(api_key=api_key)
        chat = client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[
                    get_city_state,
                    get_upcoming_events,
                    query_historical_patterns,
                    get_nearby_surplus_zones,
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


def _build_city_context(db, anomalies: list, pending_zone_ids: set, force: bool = False) -> str:
    actionable = [a for a in anomalies if a["zone"]["zone_id"] not in pending_zone_ids]

    if not actionable:
        cutoff = (datetime.utcnow() + timedelta(minutes=90)).isoformat()
        has_upcoming = db.scheduled_events.count_documents(
            {"status": "upcoming", "scheduled_time": {"$lte": cutoff}}
        )
        if not has_upcoming and not force:
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
