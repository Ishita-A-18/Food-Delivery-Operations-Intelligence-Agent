# Delivery Operations Intelligence Agent

An AI-powered operations assistant for a food delivery platform. It monitors 20 delivery zones across Bangalore in real time, detects demand-supply imbalances, and proposes targeted agent redistributions — all requiring explicit human approval before anything moves.

The agent handles the cognitive load of watching an entire city simultaneously. The manager stays in control.

---

## What It Does

Food delivery operations don't degrade gradually — they spike suddenly. A cricket match ends, a concert lets out, rain hits. Multiple zones go critical within minutes. By the time a human notices, customers have already been waiting too long.

This agent:
- Watches all 20 zones every 60 seconds for rising wait times and agent shortages
- Detects which zones are at risk and identifies the nearest available agents to move
- Proposes a redistribution with plain-English reasoning the manager can read in under 10 seconds
- Pre-positions agents before an event even starts, based on historical patterns
- Responds immediately to direct manager instructions typed in natural language
- Executes only after the manager clicks **Approve**

---

## Key Features

### Reactive Crisis Detection
When a zone's average wait time rises and its agent shortage grows, the system flags it as critical and proposes a redistribution. A card appears on the dashboard within 60 seconds of the crisis starting, naming the source zones and explaining the reasoning.

### Proactive Event Prediction
When a scheduled event is detected within 90 minutes — IPL match, concert, monsoon rain, festival — the agent cross-references historical spike patterns from real 2024 Bangalore data. It knows, for example, that RCB home games cause a 40% demand spike in HSR Layout starting 15 minutes after the match ends. It proposes pre-positioning agents before any zone goes red.

### Proximity-Aware Multi-Source Redistribution
Agents are never pulled from across the city or drained from a single zone:
- **8 km geographic constraint** — only zones within 8 km of the target are eligible sources, computed using the Haversine formula on real Bangalore coordinates
- **Multi-source split** — needed agents are distributed across up to 3 nearby zones, proportional to each zone's idle surplus
- **Reserve protection** — each source zone keeps at least 35% of its agents before contributing

### Human-in-the-Loop Approval
Every proposed action appears as a card with a one-line recommendation and 2–4 sentence reasoning. The manager clicks **Approve** or **Reject**. Nothing executes without that approval. Zones involved in a pending action are locked — the simulation cannot overwrite them while a decision is outstanding.

### Manager Chat (Natural Language Goals)
The manager can type directly into the dashboard: *"Whitefield is overwhelmed, send help"* or *"It's getting rough near the stadium."* Gemini interprets the intent, identifies the right zone, and returns a targeted approval card within 60 seconds. If Gemini is unavailable, a rule-based fallback handles the same request using zone-name matching and proximity logic.

### Live Visual Feedback
When a redistribution executes:
- **Map flash** — each affected zone briefly shows `before±delta=after` (e.g. `8−2=6`) directly on the zone circle for 5 seconds
- **Tick indicator** — a green pulse in the map header fires on every simulation cycle
- **Action log badges** — executed cards show permanent coloured `+N Zone` / `−N Zone` badges for every zone that gained or lost agents, with exact before→after counts
- **Outcome block** — once the zone recovers, the card records resolution time and estimated customer-minutes saved

### Agent Notifications
When an action executes, every moved agent receives a push notification. The notification panel shows an amber dot per agent. After 30 seconds, as agents acknowledge, the dots turn green one by one.

### Gemini Decision Engine
Every 60 seconds, Gemini 2.5 Flash reads live MongoDB Atlas data through automatic function calling. It checks zone status, queries upcoming events, looks up historical patterns, finds nearby surplus zones, and writes a structured proposal with human-readable reasoning.

**Why Gemini over pure rules:**
- Rules trigger on fixed thresholds. Gemini weighs thresholds against upcoming events — it acts earlier when a spike is predictable.
- Natural language goals map to the right zone without keyword matching.
- When multiple zones compete for the same nearby agents, Gemini sees the full city picture. Rules make independent decisions that conflict.
- The reasoning text is written for a human to read, not generated from a template.

### MongoDB Atlas MCP Server
The same tools Gemini uses internally are exposed via the Model Context Protocol. Any external MCP-compatible AI client can query live zone state, historical patterns, and upcoming events through the `/mcp/sse` endpoint.

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI decision engine | Gemini 2.5 Flash (automatic function calling) |
| Primary data store | MongoDB Atlas (M0 free tier compatible) |
| Real-time push | MongoDB Atlas change streams → WebSocket |
| MCP integration | Custom MCP server over SSE |
| Backend | FastAPI (Python 3.11) |
| Frontend | React 18 + Vite |
| Async MongoDB | Motor |
| Sync MongoDB | PyMongo (agent loop thread) |
| Geographic distance | Haversine formula on real Bangalore lat/lng |

---

## Live Demo

The agent is deployed on Google Cloud Run:

**Dashboard:** https://delivery-ops-agent-514208358262.asia-south1.run.app

The deployed version runs the full stack — FastAPI backend, React dashboard, MongoDB Atlas, and Gemini decision engine — in a single container. No local setup needed to view it.

To trigger activity on the deployed instance, run the seeder scripts locally pointed at the same MongoDB Atlas cluster (the `.env` file's `MONGO_URI` must match the deployed app's database). The change streams will push updates to any open browser session in real time.

**Inject a spike into the deployed database:**
```bash
cd seeder
python inject_spike.py ipl_spike   # triggers a crisis the deployed agent will detect and propose a fix for
```

Then open the dashboard URL and watch the approval card appear within 60 seconds.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB Atlas cluster (M0 free tier works)
- Gemini API key (Google AI Studio — free tier available)

---

## Setup

**1. Clone and configure**
```bash
git clone https://github.com/YOUR_USERNAME/delivery-ops-agent.git
cd delivery-ops-agent
cp .env.example .env
```

Edit `.env` and fill in:
```
MONGO_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/delivery_ops
GEMINI_API_KEY=your_key_here
```

**2. Create a Python virtual environment**
```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

**3. Seed the database**

This creates all 20 zones, 200 agents, historical spike patterns, and upcoming events in MongoDB Atlas.
```bash
cd seeder
python seed_all.py
cd ..
```

**4. Start the backend**
```bash
uvicorn backend.main:app --reload --port 8000
```

The backend starts three background tasks automatically:
- City simulation (recalculates zone state every 60 seconds)
- MongoDB change stream relay (pushes updates to the dashboard via WebSocket)
- Agent acknowledgement simulation (marks notifications acknowledged after 30 seconds)

**5. Start the dashboard**
```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:5173` — the animated intro page appears first, then click **Try it out →** to enter the live dashboard.

---

## Simulating Events

**Inject a demand spike (immediate crisis):**
```bash
cd seeder
python inject_spike.py ipl_spike      # HSR Layout + Indiranagar go critical
python inject_spike.py monsoon_spike  # South Bangalore residential surge
python inject_spike.py concert_spike  # Rajajinagar + Malleshwaram post-concert
python inject_spike.py diwali_spike   # Festival surge across residential zones
```

**Trigger proactive prediction (upcoming event):**
```bash
python predict_spike.py ipl 45        # IPL match in 45 min → agent pre-positions now
python predict_spike.py concert 30    # Concert ending in 30 min
```

**Send a manager goal:**
Type directly into the chat bar at the bottom of the dashboard, e.g.:
> *"Whitefield is overwhelmed, send help"*
> *"Pre-position agents near the stadium before tonight"*

The agent proposes a redistribution within 60 seconds.

---

## How the Simulation Works

Every 60 seconds, the city simulation:
1. For each unlocked zone — active agents complete ~30% of their deliveries (agents free up)
2. New orders arrive based on time of day (lunch and dinner peaks use higher arrival rates)
3. Idle agents pick up unserved orders, keeping a 35% reserve per zone
4. Wait time is recalculated from the unserved backlog
5. The simulation enforces at least 1 critical and 1 watch zone per tick (force-promotion if thresholds aren't naturally hit)

Zones involved in a pending or recently executed redistribution are **locked** and skipped by the simulation until the next action is approved. This prevents the simulation from overwriting redistribution results mid-approval.

---

## License

MIT
