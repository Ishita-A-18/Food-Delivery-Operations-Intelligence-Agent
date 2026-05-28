"""
MongoDB Atlas MCP Server for the Delivery Ops Agent.

Exposes MongoDB Atlas collections as MCP tools so the Gemini agent
can query and write data through the Model Context Protocol instead
of directly calling pymongo.

Transport: SSE (Server-Sent Events) — runs embedded in the FastAPI app.
Endpoint:  GET  /mcp/sse        (client connects here)
           POST /mcp/messages   (client sends tool calls here)
"""
import json
import os
import sys
from datetime import datetime, timedelta
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.dirname(__file__))
from db import get_db, serialize_docs, serialize_doc

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

server = Server("mongodb-atlas-delivery-ops")
sse_transport = SseServerTransport("/mcp/messages")


# ── Tool declarations ─────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_city_state",
            description=(
                "Read the live state of all 20 Bangalore delivery zones from MongoDB Atlas. "
                "Returns active_orders, idle_agents, avg_wait_minutes, and status per zone."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="query_historical_patterns",
            description=(
                "Look up historical demand spike patterns from MongoDB Atlas for a specific zone. "
                "Returns past occurrence count, avg demand spike %, resolution time, and notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "zone_id": {"type": "string", "description": "Zone ID e.g. zone_02"},
                    "event_type": {
                        "type": "string",
                        "description": "Optional: ipl_match, concert, monsoon_rain, festival_diwali, office_event, new_year_eve",
                    },
                },
                "required": ["zone_id"],
            },
        ),
        Tool(
            name="get_upcoming_events",
            description=(
                "Query MongoDB Atlas for scheduled events starting within the next 90 minutes "
                "that are likely to cause demand spikes in specific zones."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_surplus_zones",
            description=(
                "Find zones in MongoDB Atlas with surplus idle agents that can be used "
                "as a source for redistribution."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="propose_action",
            description=(
                "Write a pending agent redistribution recommendation to MongoDB Atlas "
                "for human approval on the dashboard. The action will NOT execute until "
                "a human approves it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "zone_id":         {"type": "string", "description": "Destination zone needing agents"},
                    "source_zone_id":  {"type": "string", "description": "Source zone with surplus agents"},
                    "agents_to_move":  {"type": "integer", "description": "Number of agents to move (5-15)"},
                    "recommendation":  {"type": "string", "description": "One-line summary for the approval card"},
                    "reasoning":       {"type": "string", "description": "2-4 sentence reasoning for the manager"},
                    "action_type":     {
                        "type": "string",
                        "enum": ["agent_redistribution", "preemptive_redistribution"],
                        "description": "reactive or proactive",
                    },
                },
                "required": ["zone_id", "source_zone_id", "agents_to_move", "recommendation", "reasoning"],
            },
        ),
    ]


# ── Tool implementations ──────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    db = get_db()

    if name == "get_city_state":
        zones = list(db.city_grid.find({}, {"_id": 0}))
        # Flag anomalies inline
        result = []
        for z in zones:
            shortage = z["active_orders"] - z["idle_agents"]
            z["agent_shortage"] = shortage
            z["is_critical"] = z["avg_wait_minutes"] > 35 and shortage > 5
            result.append(z)
        return [TextContent(type="text", text=json.dumps(result))]

    elif name == "query_historical_patterns":
        zone_id = arguments["zone_id"]
        event_type = arguments.get("event_type", "")
        query = {"affected_zone": zone_id}
        if event_type:
            query["event_type"] = event_type
        pattern = db.historical_patterns.find_one(query, {"_id": 0})
        if not pattern:
            pattern = db.historical_patterns.find_one({"affected_zone": zone_id}, {"_id": 0})
        if not pattern:
            return [TextContent(type="text", text=json.dumps({"found": False}))]
        return [TextContent(type="text", text=json.dumps({"found": True, **pattern}))]

    elif name == "get_upcoming_events":
        cutoff = (datetime.utcnow() + timedelta(minutes=90)).isoformat()
        events = list(db.scheduled_events.find(
            {"status": "upcoming", "scheduled_time": {"$lte": cutoff}},
            {"_id": 0},
        ))
        return [TextContent(type="text", text=json.dumps({"events": events}))]

    elif name == "get_surplus_zones":
        zones = list(db.city_grid.find({}, {"_id": 0}))
        surplus = [
            z for z in zones
            if z["idle_agents"] > z["active_orders"] * 1.5 and z["idle_agents"] > 6
        ]
        surplus.sort(key=lambda z: z["idle_agents"], reverse=True)
        return [TextContent(type="text", text=json.dumps(surplus[:5]))]

    elif name == "propose_action":
        zone_id        = arguments["zone_id"]
        source_zone_id = arguments["source_zone_id"]
        agents_to_move = int(arguments["agents_to_move"])
        recommendation = arguments["recommendation"]
        reasoning      = arguments["reasoning"]
        action_type    = arguments.get("action_type", "agent_redistribution")

        # Check not already pending
        existing = db.action_log.find_one({"trigger_zone": zone_id, "status": "pending"})
        if existing:
            return [TextContent(type="text", text=json.dumps({"status": "skipped", "reason": "already pending"}))]

        # Sample random idle agents from source zone
        agents = list(db.agents.aggregate([
            {"$match": {"current_zone": source_zone_id, "status": "idle"}},
            {"$sample": {"size": min(agents_to_move, 20)}},
        ]))
        if not agents:
            return [TextContent(type="text", text=json.dumps({"status": "skipped", "reason": "no idle agents in source zone"}))]

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
        return [TextContent(type="text", text=json.dumps({
            "status": "proposed",
            "action_id": action["action_id"],
            "agents_queued": len(moves),
        }))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# ── FastAPI route handlers (called from main.py) ──────────────────────────────

async def handle_sse(request):
    """SSE endpoint — Gemini MCP client connects here."""
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def handle_messages(request):
    """POST endpoint — client sends tool calls here."""
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
