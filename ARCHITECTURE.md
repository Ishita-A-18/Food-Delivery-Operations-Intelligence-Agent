# System Architecture — Delivery Ops Agent

## Overview

An AI operations agent for QuickBite, a food delivery platform serving 20 zones in Bangalore. The agent monitors live zone data, detects demand-supply imbalances, and proposes agent redistributions for a human manager to approve.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        MongoDB Atlas                            │
│                                                                 │
│  city_grid          agent_notifications    action_log           │
│  agents             historical_patterns    manager_goals        │
│  scheduled_events   demo_triggers          restaurants          │
└────────────┬──────────────────┬───────────────────┬────────────┘
             │                  │                   │
         sync (pymongo)    async (motor)        async (motor)
             │                  │                   │
┌────────────▼──────────┐  ┌───▼───────────────────▼────────────┐
│    agent_loop.py      │  │           main.py  (FastAPI)        │
│  (background thread)  │  │                                     │
│                       │  │  simulate_city_state()              │
│  every 60s:           │  │  · every 30s                        │
│  1. read_city_state() │  │  · orders arrive, agents complete   │
│  2. run_gemini_cycle()│  │  · 25% idle reserve per zone        │
│     → fallback if err │  │  · zones recalculate wait times     │
│  3. process goals     │  │                                     │
│  4. execute_action()  │  │  change_stream_relay()              │
│  5. close_incident()  │  │  · watches city_grid                │
│                       │  │  · watches action_log               │
└──────────┬────────────┘  │  · watches agent_notifications      │
           │               │  · pushes changes → WebSocket       │
┌──────────▼────────────┐  │                                     │
│   gemini_agent.py     │  │  simulate_acknowledgements()        │
│                       │  │  · every 10s                        │
│  Gemini tools:        │  │  · flips sent → acknowledged        │
│  · get_city_state     │  │    in agent_notifications           │
│  · get_upcoming_evts  │  │                                     │
│  · query_history      │  │  REST endpoints:                    │
│  · get_nearby_        │  │  GET  /city_state                   │
│    surplus_zones      │  │  GET  /action_log                   │
│  · propose_action     │  │  GET  /pending_actions              │
│    (multi-source)     │  │  POST /approve/:id  (→ immediate    │
│                       │  │       execute via run_in_executor)  │
│  if Gemini fails:     │  │  POST /reject/:id                   │
│  · _fallback_propose  │  │  POST /goal                         │
│  · _fallback_goal     │  │  GET  /mcp/sse                      │
└──────────┬────────────┘  └──────────────────┬──────────────────┘
           │                                  │ WebSocket + HTTP
┌──────────▼────────────┐  ┌──────────────────▼──────────────────┐
│  zone_distances.py    │  │        React Dashboard              │
│                       │  │        localhost:5173               │
│  · Haversine formula  │  │                                     │
│  · 20 zone lat/lng    │  │  CityMap          ApprovalCard      │
│  · nearby_surplus_    │  │  AgentNotifPanel  ActionLog         │
│    zones(target, 8km) │  │  ChatInput                          │
│  · multi_source_moves │  └─────────────────────────────────────┘
│    (up to 3 sources)  │
└───────────────────────┘
```

---

## Full Data Flow — One Cycle

### 1. City simulation (every 30s)
```
simulate_city_state() runs
  → active agents complete ~30% of deliveries (freed → idle)
  → new orders arrive based on time of day (2–6 lunch/dinner, 0–3 off-peak)
  → idle agents pick up orders, keeping 25% as local reserve
  → wait time = 8 + (unserved orders × 2.5) + noise, clamped 4–90 min
  → status = critical if wait > 35 AND shortage > 5
  → MongoDB city_grid updated

change_stream_relay detects the write
  → WebSocket broadcast { type: "city_grid_update", data: zone }
  → CityMap.jsx updates circle colour live (green / yellow / red)
```

### 2. Agent decision loop (every 60s)
```
agent_loop wakes up
  → read_city_state() scans city_grid
      finds zones where avg_wait > 35 AND (active_orders - idle_agents) > 5
      finds candidate source zones with idle_agents > 3
      returns ranked anomalies list

  → run_gemini_cycle(anomalies)
      Gemini calls get_city_state(), get_upcoming_events(),
      query_historical_patterns(), get_nearby_surplus_zones(zone_id),
      propose_action(zone_id, source_zone_ids="zone_02,zone_04", ...)

      propose_action:
        · splits agents_to_move across specified source zones proportionally
        · each source keeps a local reserve before contributing
        · writes action_log { status: "pending", proposed_actions: [...moves] }

      if Gemini API fails (quota / billing):
        _fallback_propose() calls multi_source_moves(zone_id, needed, all_zones)
          → zone_distances.py filters to zones within 8 km (Haversine)
          → distributes across up to 3 nearest surplus zones
        writes action_log { status: "pending" }

change_stream_relay detects action_log insert
  → WebSocket broadcast { type: "action_log_update", data: action }
  → ApprovalCard.jsx renders new card with recommendation + reasoning
```

### 3. Manager approves
```
Manager clicks Approve on dashboard
  → POST /approve/:id
  → action_log { status: "approved" }
  → run_in_executor immediately calls execute_action() (doesn't wait for next loop tick)

execute_action():
  for each agent move:
    · db.agents.update_one → current_zone = to_zone
    · db.agent_notifications.insert_one { status: "sent" }
  for each affected zone:
    · records idle_before and idle_after
    · recalculates wait time and status
    · db.city_grid.update_one
  db.action_log.update_one → {
    status: "executed",
    executed_at: ...,
    zone_changes: [{ zone_id, idle_before, idle_after, delta }, ...]
  }

change_stream fires for city_grid (per zone)
  → WebSocket { type: "city_grid_update" } — circle colour updates

change_stream fires for action_log (executed status)
  → WebSocket { type: "action_log_update", data: action_with_zone_changes }
  → CityMap.jsx reads zone_changes, flashes "idle_before±delta=idle_after"
      on each affected zone for 5 seconds (exact values, no estimation)
  → CityMap.jsx immediately updates zone circle numbers from idle_after
  → ActionLog.jsx shows permanent +N Zone / -N Zone delta badges

change_stream fires for agent_notifications (one per agent moved)
  → WebSocket { type: "agent_notification" }
  → AgentNotificationPanel shows amber dot per agent

30 seconds later:
simulate_acknowledgements() flips agent_notifications → { status: "acknowledged" }
  → change_stream fires again → dot turns green
```

### 4. Manager types a goal in chat
```
Manager types "send agents to Koramangala" → POST /goal
  → manager_goals { status: "pending" }
  → ChatInput dispatches CustomEvent "chatGoalPending"
  → ApprovalCard.jsx shows immediate CHAT-badged placeholder card

agent_loop finds manager_goals on next tick
  → run_gemini_cycle(anomalies, manager_goal="send agents to Koramangala")
      Gemini reads goal, reads city state, calls get_nearby_surplus_zones,
      proposes targeted action with multi-source redistribution
      if Gemini fails → _fallback_goal() finds zone by name,
        calls multi_source_moves(), uses same 8km proximity logic

  → manager_goals { status: "processed" }
  → action_log insert → change_stream → real approval card appears
```

### 5. Proactive event prediction
```
Manager (or script) runs: python predict_spike.py ipl 45
  → scheduled_events { status: "upcoming", scheduled_time: now + 45min }

agent_loop on next tick:
  → run_gemini_cycle sees upcoming event
  → Gemini calls query_historical_patterns("zone_02", "ipl_match")
      finds: 14 past occurrences, avg spike 40%, resolved in 14 min
  → calls get_nearby_surplus_zones("zone_02")
      returns zones within 8 km sorted by distance
  → propose_action type="preemptive_redistribution"
      "Pre-position agents in HSR Layout before IPL match"
      sources split across 2–3 nearby zones

After approve → execute_action → agents moved BEFORE the spike hits
Then: python inject_spike.py ipl_spike
  → zone goes critical but agents already there → recovers faster
```

---

## Multi-Source Proximity Logic (`zone_distances.py`)

Every redistribution — whether from Gemini or the rule-based fallback — goes through the same geographic constraint:

1. **Distance filter:** `nearby_surplus_zones(target, all_zones, max_km=8)` computes Haversine distance from the target zone to every other zone using real Bangalore lat/lng coordinates. Zones beyond 8 km are excluded — delivery agents on bikes cannot travel further in a useful time frame.

2. **Surplus filter:** A source zone is eligible only if it has idle agents above its own reserve (`idle > max(2, active_orders × 0.4)`).

3. **Proportional split:** `multi_source_moves(db, target, needed, all_zones)` takes up to 3 nearest eligible zones and distributes `needed` agents proportionally to each zone's surplus — so a zone with 12 idle contributes more than one with 4 idle, and neither is fully drained.

4. **Agent sampling:** For each source, `db.agents.aggregate($sample)` selects random idle agents from that zone to move.

Gemini follows the same constraint via the `get_nearby_surplus_zones` tool, which returns only the eligible nearby zones before `propose_action` is called.

---

## File Reference

| File | Responsibility |
|---|---|
| `backend/db.py` | MongoDB connections — `get_db()` sync for agent_loop, `get_async_db()` async for FastAPI |
| `backend/main.py` | FastAPI app — REST endpoints, WebSocket, background tasks, immediate execute on approve |
| `backend/agent_loop.py` | 60s decision loop — detect anomalies, propose, execute, close; multi-source fallbacks |
| `backend/gemini_agent.py` | Gemini function-calling with proximity-aware tools; rule-based fallback |
| `backend/zone_distances.py` | Bangalore zone coordinates, Haversine distance, `multi_source_moves()` |
| `backend/mcp_server.py` | Same tools exposed via MCP protocol for external clients |
| `backend/tools/read_city_state.py` | Scans city_grid, returns ranked anomaly list |
| `backend/tools/execute_action.py` | Moves agents, writes notifications, records zone_changes (idle_before/after), marks executed |
| `backend/tools/close_incident.py` | Checks zone recovery, writes outcome to action_log |
| `seeder/seed_all.py` | Resets all MongoDB collections to clean healthy state |
| `seeder/inject_spike.py` | Manually forces zones critical — used for demo and testing |
| `seeder/predict_spike.py` | Creates scheduled_event so agent proposes proactive card |
| `dashboard/src/components/CityMap.jsx` | SVG map, live colours, 5s before/after flash on execute using zone_changes |
| `dashboard/src/components/ApprovalCard.jsx` | Pending action cards with approve/reject; Executing state; immediate CHAT placeholder |
| `dashboard/src/components/ActionLog.jsx` | History of all actions; permanent delta badges; Resolved outcome block |
| `dashboard/src/components/AgentNotificationPanel.jsx` | Per-agent notifications, amber→green on acknowledge |
| `dashboard/src/components/ChatInput.jsx` | Manager goal input → POST /goal → CustomEvent for immediate placeholder |
| `dashboard/src/hooks/useWebSocket.js` | Shared WebSocket connection with auto-reconnect |

---

## MongoDB Collections

| Collection | What it stores |
|---|---|
| `city_grid` | Live state of all 20 zones — orders, agents, wait time, status |
| `agents` | 200 individual agents — current zone, status, last moved |
| `action_log` | All proposed/approved/executed/rejected redistributions; zone_changes on execute |
| `agent_notifications` | Per-agent move notifications, sent → acknowledged |
| `manager_goals` | Natural language goals typed in chat, pending → processed |
| `scheduled_events` | Upcoming events (IPL, concerts) for proactive planning |
| `historical_patterns` | Past spike data per zone/event — used by Gemini for context |
| `restaurants` | Restaurant locations per zone |
| `demo_triggers` | Pre-built spike scenarios for inject_spike.py |

---

## Gemini vs Fallback

| | With Gemini | Without Gemini (fallback) |
|---|---|---|
| City state | Reads all 20 zones via `get_city_state()` | `read_city_state()` scans for threshold breach |
| Source zones | `get_nearby_surplus_zones()` — within 8 km, sorted by distance | `multi_source_moves()` — same 8 km Haversine logic |
| Agent distribution | Proportional split across up to 3 named source zones | Proportional split across up to 3 nearest surplus zones |
| When to act | Weighs thresholds against upcoming events and history | Fixed threshold: wait > 35 AND shortage > 5 |
| Reasoning | Natural language, references history and event context | Template string with zone names and distances |
| Proactive | Reads upcoming events, queries history, sizes move from spike % | `_fallback_proactive()` checks events within 90 min |
| Manager goal | Understands intent, picks right zone from natural language | Matches zone name in text, falls back to worst-wait zone |

Gemini is enabled by setting `GEMINI_API_KEY` in `.env`. If the key is missing or returns a quota error, the system automatically uses the fallback — all features still work, only the reasoning quality and threshold flexibility differ.
