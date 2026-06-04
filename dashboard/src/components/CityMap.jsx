import { useState, useEffect, useRef } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS  = import.meta.env.VITE_WS_URL  || "ws://localhost:8000/ws";

// SVG positions derived from lat/lng (viewBox 0 0 700 500)
const ZONE_POSITIONS = {
  zone_01: { x: 359, y: 300 }, // Koramangala
  zone_02: { x: 387, y: 334 }, // HSR Layout
  zone_03: { x: 391, y: 240 }, // Indiranagar
  zone_04: { x: 330, y: 327 }, // BTM Layout
  zone_05: { x: 612, y: 251 }, // Whitefield
  zone_06: { x: 297, y: 314 }, // Jayanagar
  zone_07: { x: 504, y: 266 }, // Marathahalli
  zone_08: { x: 470, y: 448 }, // Electronic City
  zone_09: { x: 305, y: 360 }, // Bannerghatta Road
  zone_10: { x: 222, y: 222 }, // Rajajinagar
  zone_11: { x: 245, y: 203 }, // Malleshwaram
  zone_12: { x: 303, y:  64 }, // Yelahanka
  zone_13: { x: 281, y: 341 }, // JP Nagar
  zone_14: { x: 304, y: 157 }, // Hebbal
  zone_15: { x: 480, y: 349 }, // Sarjapur Road
  zone_16: { x: 464, y: 313 }, // Bellandur
  zone_17: { x: 203, y: 314 }, // Banashankari
  zone_18: { x: 312, y: 242 }, // MG Road
  zone_19: { x: 305, y: 218 }, // Cunningham Road
  zone_20: { x:  75, y: 339 }, // Kengeri
};

const STATUS_COLOR = {
  normal:   "#22c55e",
  watch:    "#f59e0b",
  critical: "#ef4444",
};

export function CityMap() {
  const [zones, setZones] = useState([]);
  const [tooltip, setTooltip] = useState(null);
  const [flashDeltas, setFlashDeltas] = useState({});
  const flashedActions = useRef(new Set());
  const { messages } = useWebSocket(WS);

  // Initial load
  useEffect(() => {
    fetch(`${API}/city_state`)
      .then((r) => r.json())
      .then(setZones)
      .catch(() => {});
  }, []);

  // Poll every 10s
  useEffect(() => {
    const id = setInterval(() => {
      fetch(`${API}/city_state`)
        .then((r) => r.json())
        .then(setZones)
        .catch(() => {});
    }, 10000);
    return () => clearInterval(id);
  }, []);

  // Live updates via WebSocket.
  // messages are newest-first → take only the latest per zone.
  // If a zone was just redistributed (_action_executed_at stamp), skip any
  // city_grid_update whose last_updated predates the redistribution.
  useEffect(() => {
    const cityUpdates = messages.filter((m) => m.type === "city_grid_update");
    if (cityUpdates.length === 0) return;
    const latestByZone = {};
    cityUpdates.forEach((msg) => {
      if (!latestByZone[msg.data.zone_id]) latestByZone[msg.data.zone_id] = msg.data;
    });
    setZones((prev) =>
      prev.map((z) => {
        const incoming = latestByZone[z.zone_id];
        if (!incoming) return z;
        if (z._action_executed_at && incoming.last_updated <= z._action_executed_at) return z;
        const { _action_executed_at, ...rest } = incoming;
        return rest;
      })
    );
  }, [messages]);

  // Flash before→after on zones when an action executes (once per action)
  useEffect(() => {
    const executed = messages.filter(
      (m) => m.type === "action_log_update" && m.data.status === "executed"
      && !flashedActions.current.has(m.data.action_id)
    );
    if (executed.length === 0) return;
    executed.forEach((msg) => {
      flashedActions.current.add(msg.data.action_id);

      // Use zone_changes (exact values) or fall back to proposed_actions
      let changes = msg.data.zone_changes || [];
      if (changes.length === 0) {
        const deltaMap = {};
        (msg.data.proposed_actions || []).forEach((move) => {
          if (move.type !== "move_agent") return;
          deltaMap[move.from_zone] = (deltaMap[move.from_zone] || 0) - 1;
          deltaMap[move.to_zone]   = (deltaMap[move.to_zone]   || 0) + 1;
        });
        changes = Object.entries(deltaMap).map(([zone_id, delta]) => ({
          zone_id, delta, idle_before: null, idle_after: null,
        }));
      }
      if (changes.length === 0) return;

      // Stamp executed_at so stale city_grid_updates can't overwrite this value
      const executedAt = msg.data.executed_at;
      setZones((prev) =>
        prev.map((z) => {
          const change = changes.find((c) => c.zone_id === z.zone_id);
          if (!change || change.idle_after === null) return z;
          return { ...z, idle_agents: change.idle_after, _action_executed_at: executedAt };
        })
      );

      const newDeltas = {};
      changes.forEach(({ zone_id, idle_before, idle_after, delta }) => {
        newDeltas[zone_id] = { delta, idle_before, idle_after };
      });
      setFlashDeltas((prev) => ({ ...prev, ...newDeltas }));
      setTimeout(() => {
        setFlashDeltas((prev) => {
          const next = { ...prev };
          changes.forEach(({ zone_id }) => delete next[zone_id]);
          return next;
        });
      }, 5000);
    });
  }, [messages]);

  const zoneMap = Object.fromEntries(zones.map((z) => [z.zone_id, z]));

  return (
    <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
      <div className="section-header">
        City Grid — Bangalore
        <span style={{ color: "var(--text-secondary)", fontSize: 12, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>
          {zones.filter((z) => z.status === "critical").length} critical &nbsp;·&nbsp;
          {zones.filter((z) => z.status === "watch").length} watch
        </span>
      </div>

      <svg
        viewBox="0 0 700 500"
        width="100%"
        height="100%"
        style={{ display: "block" }}
      >
        {/* Background grid lines */}
        {[100, 200, 300, 400, 500, 600].map((x) => (
          <line key={`vl${x}`} x1={x} y1={0} x2={x} y2={500} stroke="#1f2d45" strokeWidth={0.5} />
        ))}
        {[100, 200, 300, 400].map((y) => (
          <line key={`hl${y}`} x1={0} y1={y} x2={700} y2={y} stroke="#1f2d45" strokeWidth={0.5} />
        ))}

        {Object.entries(ZONE_POSITIONS).map(([zone_id, pos]) => {
          const zone = zoneMap[zone_id];
          if (!zone) return null;
          const color = STATUS_COLOR[zone.status] || "#4e5a6e";
          const isPulsing = zone.status === "critical";

          return (
            <g
              key={zone_id}
              onMouseEnter={() => setTooltip({ zone, pos })}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: "pointer" }}
            >
              {/* Pulse ring for critical zones */}
              {isPulsing && (
                <circle cx={pos.x} cy={pos.y} r={22} fill="none" stroke={color} strokeWidth={1.5} opacity={0.3}>
                  <animate attributeName="r" from="18" to="28" dur="1.5s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.4" to="0" dur="1.5s" repeatCount="indefinite" />
                </circle>
              )}
              {/* Zone circle — dashed when locked by a pending/executed redistribution */}
              <circle
                cx={pos.x}
                cy={pos.y}
                r={18}
                fill={color + "22"}
                stroke={color}
                strokeWidth={zone.locked ? 2 : 1.5}
                strokeDasharray={zone.locked ? "4 2" : "none"}
              />
              {/* Idle agent count */}
              <text
                x={pos.x}
                y={pos.y + 1}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={color}
                fontSize={11}
                fontWeight={600}
                fontFamily="Inter, sans-serif"
              >
                {zone.idle_agents}
              </text>
              {/* Zone label */}
              <text
                x={pos.x}
                y={pos.y + 25}
                textAnchor="middle"
                fill="#8892a4"
                fontSize={8.5}
                fontFamily="Inter, sans-serif"
              >
                {zone.name.split(" ")[0]}
              </text>

              {/* before→after flash when agents redistributed */}
              {flashDeltas[zone_id] !== undefined && (() => {
                const { delta, idle_before, idle_after } = flashDeltas[zone_id];
                const sign  = delta > 0 ? `+${delta}` : `${delta}`;
                const col   = delta > 0 ? "#22c55e" : "#ef4444";
                return (
                  <text
                    x={pos.x}
                    y={pos.y - 26}
                    textAnchor="middle"
                    fill={col}
                    fontSize={11}
                    fontWeight={700}
                    fontFamily="Inter, sans-serif"
                    style={{ animation: "slide-in 0.3s ease" }}
                  >
                    {idle_before}{sign}={idle_after}
                  </text>
                );
              })()}
            </g>
          );
        })}
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div
          style={{
            position: "absolute",
            left: `${(tooltip.pos.x / 700) * 100}%`,
            top: `${(tooltip.pos.y / 500) * 100}%`,
            transform: "translate(-50%, -115%)",
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "10px 14px",
            pointerEvents: "none",
            whiteSpace: "nowrap",
            zIndex: 10,
            fontSize: 12,
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{tooltip.zone.name}</div>
          <div style={{ color: "var(--text-secondary)" }}>
            {tooltip.zone.active_orders} orders &nbsp;·&nbsp; {tooltip.zone.idle_agents} idle agents
          </div>
          <div style={{ color: "var(--text-secondary)" }}>
            Avg wait: <strong style={{ color: "var(--text-primary)" }}>{tooltip.zone.avg_wait_minutes} min</strong>
          </div>
          <div style={{ marginTop: 4 }}>
            <span className={`badge badge-${tooltip.zone.status}`}>{tooltip.zone.status}</span>
          </div>
        </div>
      )}

      {/* Legend */}
      <div style={{ position: "absolute", bottom: 12, left: 16, display: "flex", gap: 16, fontSize: 11, color: "var(--text-secondary)" }}>
        {[["normal", "#22c55e"], ["watch", "#f59e0b"], ["critical", "#ef4444"]].map(([label, color]) => (
          <span key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
            {label}
          </span>
        ))}
        <span style={{ color: "var(--text-tertiary)" }}>· number = idle agents</span>
      </div>
    </div>
  );
}
