import asyncio
import random
import sys
import os
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(__file__))
from db import get_db, get_async_db, serialize_doc, serialize_docs
from mcp_server import handle_sse, handle_messages

app = FastAPI(title="Delivery Ops Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

clients: list[WebSocket] = []


# ── MCP endpoints (MongoDB Atlas MCP Server) ──────────────────────────────────

@app.get("/mcp/sse")
async def mcp_sse(request: Request):
    """SSE endpoint — Gemini MCP client connects here to get MongoDB tools."""
    await handle_sse(request)


@app.post("/mcp/messages")
async def mcp_messages(request: Request):
    """POST endpoint — Gemini MCP client sends tool calls here."""
    await handle_messages(request)


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.remove(ws)


async def broadcast(message: dict):
    dead = []
    for client in clients:
        try:
            await client.send_json(message)
        except Exception:
            dead.append(client)
    for c in dead:
        clients.remove(c)


# ── Background tasks ───────────────────────────────────────────────────────────

async def change_stream_relay():
    """Watch MongoDB collections and push every change to connected dashboards."""
    db = get_async_db()

    async def watch(collection_name: str, message_type: str):
        try:
            async with db[collection_name].watch(full_document="updateLookup") as stream:
                async for change in stream:
                    doc = change.get("fullDocument")
                    if doc:
                        await broadcast({"type": message_type, "data": serialize_doc(doc)})
        except Exception as exc:
            print(f"[change_stream_relay] {collection_name} error: {exc}", flush=True)

    await asyncio.gather(
        watch("action_log", "action_log_update"),
        watch("agent_notifications", "agent_notification"),
        watch("city_grid", "city_grid_update"),
    )


async def simulate_city_state():
    """Every 30s: orders arrive, complete, agents go idle/active — zones heat up and cool down naturally."""
    db = get_async_db()
    while True:
        await asyncio.sleep(60)
        try:
            # IST = UTC + 5:30 — determine time-of-day arrival rate
            ist_hour = (datetime.utcnow().hour + 5) % 24
            if 7 <= ist_hour < 10:
                arrival = (1, 4)   # morning
            elif 12 <= ist_hour < 15:
                arrival = (2, 6)   # lunch rush
            elif 19 <= ist_hour < 23:
                arrival = (2, 6)   # dinner rush
            elif ist_hour >= 23 or ist_hour < 2:
                arrival = (0, 2)   # late night
            else:
                arrival = (0, 3)   # off-peak

            zones = await db.city_grid.find().to_list(None)
            pending = []

            for zone in zones:
                if zone.get("locked"):
                    continue
                total_agents  = zone["total_agents"]
                active_orders = zone["active_orders"]
                idle_agents   = zone["idle_agents"]
                active_agents = total_agents - idle_agents

                # Step 1 — active agents finish deliveries (~30% per tick)
                completed    = int(active_agents * random.uniform(0.25, 0.35))
                active_orders = max(0, active_orders - completed)
                idle_agents   = min(total_agents, idle_agents + completed)
                active_agents = total_agents - idle_agents

                # Step 2 — new orders arrive
                new_orders   = random.randint(*arrival)
                active_orders += new_orders

                # Step 3 — idle agents pick up orders, keeping 35% as reserve
                reserve      = max(2, int(total_agents * 0.35))
                assignable   = max(0, idle_agents - reserve)
                can_assign   = min(assignable, active_orders)
                idle_agents  = max(reserve, idle_agents - can_assign)
                active_agents = total_agents - idle_agents

                # Step 4 — wait time based on unserved backlog
                unserved = max(0, active_orders - active_agents)
                wait = round(min(max(8.0 + unserved * 2.5 + random.uniform(-2, 2), 4.0), 90.0), 1)
                shortage = active_orders - idle_agents

                pending.append({
                    "zone_id":       zone["zone_id"],
                    "active_orders": active_orders,
                    "idle_agents":   idle_agents,
                    "active_agents": active_agents,
                    "avg_wait_minutes": wait,
                    "_severity":     wait * 2 + max(0, shortage),
                    "_raw_critical": wait > 35 and shortage > 5,
                    "_raw_watch":    wait > 22,
                })

            # Enforce 1–2 critical, 1–3 watch. Sort worst-first so the worst zones
            # earn elevated status first; force-promote if nothing hits thresholds.
            pending.sort(key=lambda z: z["_severity"], reverse=True)
            critical_slots, watch_slots = 2, 3
            statuses = []
            crit_count = watch_count = 0
            for u in pending:
                if u["_raw_critical"] and critical_slots > 0:
                    s = "critical"; critical_slots -= 1; crit_count += 1
                elif u["_raw_watch"] and watch_slots > 0:
                    s = "watch"; watch_slots -= 1; watch_count += 1
                else:
                    s = "normal"
                statuses.append(s)

            locked_ids = {z["zone_id"] for z in zones if z.get("locked")}
            if crit_count < 1:
                for i, u in enumerate(pending):
                    if statuses[i] != "critical" and u["zone_id"] not in locked_ids:
                        if statuses[i] == "watch":
                            watch_count -= 1
                        statuses[i] = "critical"; crit_count += 1
                        break
            if watch_count < 1:
                for i, u in enumerate(pending):
                    if statuses[i] == "normal" and u["zone_id"] not in locked_ids:
                        statuses[i] = "watch"; watch_count += 1
                        break

            now_iso = datetime.utcnow().isoformat()
            for u, status in zip(pending, statuses):
                await db.city_grid.update_one(
                    {"zone_id": u["zone_id"]},
                    {"$set": {
                        "active_orders":    u["active_orders"],
                        "idle_agents":      u["idle_agents"],
                        "active_agents":    u["active_agents"],
                        "avg_wait_minutes": u["avg_wait_minutes"],
                        "status":           status,
                        "last_updated":     now_iso,
                    }},
                )
        except Exception as exc:
            print(f"[simulate_city_state] error: {exc}", flush=True)


async def simulate_acknowledgements():
    """Simulate agents tapping 'got it' 30 seconds after notification."""
    db = get_async_db()
    while True:
        try:
            cutoff = (datetime.utcnow() - timedelta(seconds=30)).isoformat()
            await db.agent_notifications.update_many(
                {"status": "sent", "sent_at": {"$lt": cutoff}},
                {"$set": {
                    "status": "acknowledged",
                    "acknowledged_at": datetime.utcnow().isoformat(),
                }},
            )
        except Exception as exc:
            print(f"[simulate_acknowledgements] error: {exc}", flush=True)
        await asyncio.sleep(10)


def _run_agent_loop():
    from agent_loop import agent_loop
    agent_loop()


def _process_goal_now(goal_text: str) -> None:
    """Process a manager chat goal immediately in a background thread."""
    from tools.read_city_state import read_city_state
    from gemini_agent import run_gemini_cycle
    from agent_loop import _fallback_goal
    from uuid import uuid4
    db = get_db()
    try:
        anomalies = read_city_state(db)
        ids_before = {a["action_id"] for a in db.action_log.find({"status": "pending"}, {"action_id": 1})}
        run_gemini_cycle(db, anomalies, manager_goal=goal_text)
        ids_after = {a["action_id"] for a in db.action_log.find({"status": "pending"}, {"action_id": 1})}
        if not ids_after - ids_before:
            _fallback_goal(db, goal_text)
        ids_final = {a["action_id"] for a in db.action_log.find({"status": "pending"}, {"action_id": 1})}
        if not ids_final - ids_before:
            db.agent_notifications.insert_one({
                "notification_id": f"notif_{uuid4().hex[:6]}",
                "agent_id": "system",
                "action_id": None,
                "message": f"Cannot fulfill \"{goal_text[:60]}\": no nearby zones have available agents to redistribute.",
                "status": "info",
                "sent_at": datetime.utcnow().isoformat(),
                "acknowledged_at": None,
            })
        db.manager_goals.update_one(
            {"goal": goal_text, "status": "pending"},
            {"$set": {"status": "processed"}},
        )
        print(f"[goal] processed immediately: {goal_text[:60]}", flush=True)
    except Exception as exc:
        print(f"[goal] error processing: {exc}", flush=True)


@app.on_event("startup")
async def startup():
    loop = asyncio.get_event_loop()
    # Agent loop is sync (pymongo) — run in thread so it doesn't block FastAPI
    loop.run_in_executor(None, _run_agent_loop)
    asyncio.create_task(change_stream_relay())
    asyncio.create_task(simulate_acknowledgements())
    asyncio.create_task(simulate_city_state())


# ── REST endpoints ─────────────────────────────────────────────────────────────

@app.get("/city_state")
async def get_city_state():
    db = get_async_db()
    zones = await db.city_grid.find().to_list(None)
    return serialize_docs(zones)


@app.get("/pending_actions")
async def get_pending_actions():
    db = get_async_db()
    actions = await db.action_log.find({"status": "pending"}).to_list(None)
    return serialize_docs(actions)


@app.get("/action_log")
async def get_action_log():
    db = get_async_db()
    actions = await db.action_log.find().sort("created_at", -1).limit(50).to_list(None)
    return serialize_docs(actions)


@app.post("/approve/{action_id}")
async def approve_action(action_id: str, body: dict = {}):
    from tools.execute_action import execute_action as _execute
    db_async = get_async_db()
    db_sync  = get_db()
    # Release all zones locked by previous redistributions — new approval is the next intervention
    await db_async.city_grid.update_many({"locked": True}, {"$unset": {"locked": ""}})
    await db_async.action_log.update_one(
        {"action_id": action_id},
        {"$set": {
            "status": "approved",
            "approved_at": datetime.utcnow().isoformat(),
            "approved_by": "manager",
            "modification": body.get("modification"),
        }},
    )
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, lambda: _execute(db_sync, action_id))
    return {"status": "approved"}


@app.post("/reject/{action_id}")
async def reject_action(action_id: str):
    db = get_async_db()
    action = await db.action_log.find_one({"action_id": action_id})
    if action:
        zone_ids = {action.get("zone_id")}
        for move in action.get("proposed_actions", []):
            if move.get("type") == "move_agent":
                zone_ids.add(move.get("from_zone"))
        zone_ids.discard(None)
        if zone_ids:
            await db.city_grid.update_many(
                {"zone_id": {"$in": list(zone_ids)}},
                {"$unset": {"locked": "", "locked_until": ""}},
            )
    await db.action_log.update_one(
        {"action_id": action_id},
        {"$set": {"status": "rejected"}},
    )
    return {"status": "rejected"}


@app.post("/goal")
async def receive_goal(body: dict):
    goal_text = body.get("goal", "").strip()
    if not goal_text:
        return {"status": "error", "message": "goal text required"}
    db_async = get_async_db()
    await db_async.manager_goals.insert_one({
        "goal": goal_text,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    })
    # Process immediately instead of waiting for the 60s loop tick
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, lambda: _process_goal_now(goal_text))
    return {"status": "received"}


# ── Serve React frontend (must be last) ───────────────────────────────────────

import os as _os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_static = _os.path.join(_os.path.dirname(__file__), "static")
if _os.path.isdir(_static):
    app.mount("/assets", StaticFiles(directory=f"{_static}/assets"), name="assets")

    @app.get("/{_full_path:path}")
    async def serve_spa(_full_path: str = ""):
        return FileResponse(f"{_static}/index.html")
