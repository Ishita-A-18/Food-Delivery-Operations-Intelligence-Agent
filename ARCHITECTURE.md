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
│  2. run_gemini_cycle()│  │  · zones recalculate wait times     │
│     → fallback if err │  │                                     │
│  3. process goals     │  │  change_stream_relay()              │
│  4. execute_action()  │  │  · watches city_grid                │
│  5. close_incident()  │  │  · watches action_log               │
│                       │  │  · watches agent_notifications      │
└──────────┬────────────┘  │  · pushes changes → WebSocket       │
           │               │                                     │
┌──────────▼────────────┐  │  simulate_acknowledgements()        │
│   gemini_agent.py     │  │  · every 10s                        │
│                       │  │  · flips sent → acknowledged        │
│  Gemini tools:        │  │    in agent_notifications           │
│  · get_city_state     │  │                                     │
│  · get_upcoming_evts  │  │  REST endpoints:                    │
│  · query_history      │  │  GET  /city_state                   │
│  · get_surplus_zones  │  │  GET  /action_log                   │
│  · propose_action     │  │  GET  /pending_actions              │
│                       │  │  POST /approve/:id                  │
│  if Gemini fails:     │  │  POST /reject/:id                   │
│  · _fallback_propose  │  │  POST /goal                         │
│  · _fallback_goal     │  │  GET  /mcp/sse                      │
└───────────────────────┘  └──────────────────┬──────────────────┘
                                              │ WebSocket + HTTP
                           ┌──────────────────▼──────────────────┐
                           │        React Dashboard              │
                           │        localhost:5173               │
                           │                                     │
                           │  CityMap          ApprovalCard      │
                           │  AgentNotifPanel  ActionLog         │
                           │  ChatInput                          │
                           └─────────────────────────────────────┘
```

---

## Full Data Flow — One Cycle

### 1. City simulation (every 30s)
```
simulate_city_state() runs
  → active agents complete ~30% of deliveries (freed → idle)
  → new orders arrive based on time of day (2–6 lunch/dinner, 0–3 off-peak)
  → ALL idle agents pick up from full order backlog
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
      query_historical_patterns(), get_surplus_zones(), propose_action()
      writes action_log { status: "pending" }

      if Gemini API fails (quota / billing):
        _fallback_propose() applies rule-based logic instead
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

agent_loop (next 60s tick) finds approved actions
  → execute_action(action_id):
      for each agent move:
        · db.agents.update_one → current_zone = to_zone
        · db.agent_notifications.insert_one { status: "sent" }
      db.action_log.update_one → status: "executed"

change_stream fires for agent_notifications (one per agent moved)
  → WebSocket { type: "agent_notification", data: notification }
  → AgentNotificationPanel shows amber dot per agent

30 seconds later:
simulate_acknowledgements() flips agent_notifications → { status: "acknowledged" }
  → change_stream fires again with updated document
  → same notification_id merges in panel → dot turns green
```

### 4. Manager types a goal in chat
```
Manager types "send agents to Koramangala" → POST /goal
  → manager_goals { status: "pending" }

agent_loop finds it on next tick
  → run_gemini_cycle(anomalies, manager_goal="send agents to Koramangala")
      Gemini reads goal, reads city state, proposes targeted action
      if Gemini fails → _fallback_goal() finds zone by name, proposes card

  → manager_goals { status: "processed" }
  → ApprovalCard shows new card for that zone
```

### 5. Proactive event prediction
```
Manager (or script) runs: python predict_spike.py ipl 45
  → scheduled_events { status: "upcoming", scheduled_time: now + 45min }

agent_loop on next tick:
  → run_gemini_cycle sees upcoming event
  → Gemini calls query_historical_patterns("zone_02", "ipl_match")
      finds: 14 past occurrences, avg spike 40%, resolved in 14 min
  → propose_action type="preemptive_redistribution"
      "Pre-position 12 agents in HSR Layout before IPL match"

After approve → execute → agents moved BEFORE the spike hits
Then: python inject_spike.py ipl_spike
  → zone goes critical but agents already there → recovers faster
```

---

## File Reference

| File | Responsibility |
|---|---|
| `backend/db.py` | MongoDB connections — `get_db()` sync for agent_loop, `get_async_db()` async for FastAPI |
| `backend/main.py` | FastAPI app — REST endpoints, WebSocket, background tasks |
| `backend/agent_loop.py` | 60s decision loop — detect anomalies, propose, execute, close |
| `backend/gemini_agent.py` | Gemini function-calling + fallback rule engine |
| `backend/mcp_server.py` | Same tools exposed via MCP protocol for external clients |
| `backend/tools/read_city_state.py` | Scans city_grid, returns ranked anomaly list |
| `backend/tools/execute_action.py` | Moves agents in DB, writes notifications, marks executed |
| `backend/tools/close_incident.py` | Checks zone recovery, writes outcome to action_log |
| `seeder/seed_all.py` | Resets all 10 MongoDB collections to clean healthy state |
| `seeder/inject_spike.py` | Manually forces zones critical — used for demo and testing |
| `seeder/predict_spike.py` | Creates scheduled_event so agent proposes proactive card |
| `dashboard/src/components/CityMap.jsx` | SVG map of 20 zones, live colour updates via WebSocket |
| `dashboard/src/components/ApprovalCard.jsx` | Shows pending actions, approve/reject buttons |
| `dashboard/src/components/ActionLog.jsx` | History of all actions and their outcomes |
| `dashboard/src/components/AgentNotificationPanel.jsx` | Per-agent notifications, amber→green on acknowledge |
| `dashboard/src/components/ChatInput.jsx` | Manager goal input → POST /goal |
| `dashboard/src/hooks/useWebSocket.js` | Shared WebSocket connection with auto-reconnect |

---

## MongoDB Collections

| Collection | What it stores |
|---|---|
| `city_grid` | Live state of all 20 zones — orders, agents, wait time, status |
| `agents` | 200 individual agents — current zone, status, last moved |
| `action_log` | All proposed/approved/executed/rejected redistributions |
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
| Source zone | Gemini picks best source using context | Any zone with `idle_agents > 3` |
| Reasoning | Natural language, references history | Template string with raw numbers |
| Proactive | Reads upcoming events, queries history | `_fallback_proactive()` checks events within 90 min |
| Manager goal | Understands intent, picks right zone | Matches zone name in text, falls back to worst zone |

Gemini is enabled by setting `GEMINI_API_KEY` in `.env`. If the key is missing or returns a quota error, the system automatically uses fallback — all features still work.
