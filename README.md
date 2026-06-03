# Delivery Ops Agent

An AI operations assistant for a food delivery platform that watches the entire city grid so the manager doesn't have to. It monitors 20 delivery zones in real time, continuously tracking active orders, idle delivery agents, and average wait times. When a zone tips into crisis — too many orders, not enough agents — the agent detects it and proposes a fix. When a known event is approaching, it prepares before the crisis even starts.

The manager stays in control. The agent never acts on its own — every action requires explicit human approval. The agent handles the cognitive load of watching 20 zones simultaneously; the human makes the call.

---

## How It Works

### City Simulation
Every 30 seconds, orders arrive across all 20 zones based on time of day. Active agents complete deliveries and free up. Wait times are recalculated based on how many orders still have no agent assigned. This keeps the system in a realistic, constantly changing state.

### Gemini Decision Engine
Every 60 seconds, Gemini reads the live MongoDB Atlas data through function calling. It checks which zones are critical, looks up upcoming events, queries historical spike patterns, identifies surplus zones, and writes a proposal. It explains its reasoning in plain English so the manager can act in under 10 seconds.

### Human-in-the-Loop Approval
Every proposed action appears as a card on the dashboard. The manager reads the reasoning, clicks Approve or Reject. Only after approval does the agent execute — moving agents in the database, notifying each affected agent.

### Reactive Response
When a zone exceeds 35 minutes average wait with more than 5 unserved orders, Gemini flags it as critical and proposes agent redistribution from a surplus zone. The card appears within 60 seconds of the crisis starting.

### Proactive Prediction
When a scheduled event is detected within 90 minutes — an IPL match, a concert, monsoon rain — Gemini cross-references 13 historical patterns built from real 2024 Bangalore event data. It knows that RCB home games cause a 40% spike in HSR Layout 15 minutes after the match ends, resolved in 14 minutes via redistribution. It proposes pre-positioning agents before any zone goes red.

### MongoDB Atlas MCP Server
The same tools Gemini uses internally are exposed via the Model Context Protocol, making the operational data accessible to any external AI client.

### Live Dashboard
A React dashboard shows the city map with live zone colours updating via MongoDB change streams over WebSocket. Agent notifications cascade in when an action executes — amber dots per agent, turning green as each acknowledges. The manager can also type a natural language goal directly into the chat input and get a targeted proposal within 60 seconds.

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

---

## License

MIT
