# Delivery Ops Agent

An AI operations assistant for a food delivery platform that watches the entire city grid so the manager doesn't have to. It monitors 20 delivery zones in real time, continuously tracking active orders, idle delivery agents, and average wait times. When a zone tips into crisis — too many orders, not enough agents — the agent detects it and proposes a fix. When a known event is approaching, it prepares before the crisis even starts.

The manager stays in control. The agent never acts on its own — every action requires explicit human approval. The agent handles the cognitive load of watching 20 zones simultaneously; the human makes the call.

---

## How It Works

### City Simulation
Every 30 seconds, orders arrive across all 20 zones based on time of day. Active agents complete deliveries and free up. Wait times are recalculated based on how many orders still have no agent assigned. A 25% idle reserve is maintained per zone so no area fully drains. This keeps the system in a realistic, constantly changing state.

### Gemini Decision Engine
Every 60 seconds, Gemini reads the live MongoDB Atlas data through function calling. It checks which zones are critical, looks up upcoming events, queries historical spike patterns, finds geographically nearby surplus zones, and writes a proposal. It explains its reasoning in plain English so the manager can act in under 10 seconds.

**Why Gemini instead of pure rules:**
- Rules trigger on a fixed threshold. Gemini weighs the threshold against upcoming events and historical patterns — it acts earlier when it knows a spike is coming.
- Manager chat goals are natural language. "It's getting rough near the stadium" maps to the right zone without a keyword match.
- When two zones compete for the same nearby agents, Gemini sees the global picture and prioritises. Rules make independent decisions that can conflict.
- The reasoning text on each approval card is written for a human to read and trust — not a template string.

### Multi-Source Proximity-Aware Redistribution
When agents need to be moved, the system never drains a single zone or pulls from across the city. Instead:

- **Geographic constraint:** Only zones within **8 km** of the target are eligible as sources, computed using the Haversine formula on real Bangalore lat/lng coordinates. Delivery agents on bikes cannot realistically travel further.
- **Multi-source split:** Needed agents are distributed across up to 3 nearby zones proportionally to each zone's idle surplus. No single zone is drained.
- **Reserve protection:** Each source zone keeps at least 25% of its agents as a local reserve before contributing to a redistribution.

This applies to both Gemini proposals and the rule-based fallback — the same distance logic runs either way.

### Human-in-the-Loop Approval
Every proposed action appears as a card on the dashboard with a one-line recommendation and 2–4 sentence reasoning that names which zones agents come from and why. The manager clicks Approve or Reject. Only after approval does the agent execute — moving agents in the database, notifying each affected delivery agent.

### Reactive Response
When a zone exceeds 35 minutes average wait with more than 5 unserved orders, the agent flags it as critical and proposes an agent redistribution from nearby surplus zones. The card appears within 60 seconds of the crisis starting.

### Proactive Prediction
When a scheduled event is detected within 90 minutes — an IPL match, a concert, monsoon rain — the agent cross-references 13 historical patterns built from real 2024 Bangalore event data. It knows that RCB home games cause a 40% spike in HSR Layout 15 minutes after the match ends, resolved in 14 minutes via redistribution. It proposes pre-positioning agents before any zone goes red.

### Live Visual Feedback
When a redistribution executes, the dashboard shows exactly what happened:

- **City map flash:** Each affected zone briefly shows `before±delta=after` (e.g. `8+3=11`) directly on the zone circle, using the exact values recorded at execution time — not estimated from live state. Stays for 5 seconds.
- **Circle update:** The idle agent count inside each zone circle updates immediately on execution, before the next simulation tick.
- **Action log delta badges:** Every executed action card permanently shows coloured `+N Zone` / `-N Zone` badges indicating which zones gained and lost agents. These persist even after the action is marked resolved.
- **Outcome block:** Once the zone recovers, the card shows resolution time and estimated customer-minutes saved.

### Agent Notifications
When an action executes, each moved agent receives a notification. The panel shows an amber dot per agent. Thirty seconds later, as agents acknowledge, dots turn green one by one.

### Manager Chat
The manager can type a natural language goal directly into the dashboard — "Whitefield is overwhelmed, send help" — and receive a targeted approval card within 60 seconds. Gemini interprets the intent; if Gemini is unavailable, the fallback matches zone names and uses the same proximity-aware redistribution.

### MongoDB Atlas MCP Server
The same tools Gemini uses internally are exposed via the Model Context Protocol, making the operational data accessible to any external AI client.

---

## Technologies Used

| Technology | Role |
|---|---|
| Gemini 2.5 Flash | Decision engine with automatic function calling |
| MongoDB Atlas | Primary data store, change streams for real-time push |
| MongoDB MCP Server | Model Context Protocol integration |
| FastAPI | Backend with WebSocket and REST |
| React + Vite | Live operations dashboard |
| Motor (async) + PyMongo (sync) | Dual MongoDB drivers for async and threaded contexts |
| Haversine formula | Geographic distance between Bangalore zones for proximity-aware redistribution |

---

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB Atlas cluster (M0 free tier works)
- Gemini API key from Google Cloud

### Setup

**1. Clone and configure:**
```bash
git clone https://github.com/YOUR_USERNAME/delivery-ops-agent.git
cd delivery-ops-agent
cp .env.example .env
# Fill in MONGO_URI and GEMINI_API_KEY in .env
```

**2. Backend:**
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

**3. Seed the database:**
```bash
cd seeder
python seed_all.py
cd ..
```

**4. Start backend:**
```bash
uvicorn backend.main:app --reload --port 8000
```

**5. Start dashboard:**
```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:5173`

---

## Demo

**Inject a live spike:**
```bash
cd seeder
python inject_spike.py ipl_spike      # HSR Layout + Indiranagar go critical
python inject_spike.py monsoon_spike  # South Bangalore residential surge
python inject_spike.py concert_spike  # Rajajinagar + Malleshwaram post-concert
python inject_spike.py diwali_spike   # Festival surge across residential zones
```

**Trigger proactive prediction:**
```bash
python predict_spike.py ipl 45        # IPL match in 45 min — agent pre-positions
python predict_spike.py concert 30    # Concert ending in 30 min
```

**Send a manager goal via chat:**
Type directly in the dashboard chat bar — e.g. *"Whitefield is overwhelmed, send help"*

The agent will propose a redistribution sourcing agents from nearby zones within 8 km, split across up to 3 sources proportionally to their idle surplus.

---

## License

MIT
