import { useState, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS  = import.meta.env.VITE_WS_URL  || "ws://localhost:8000/ws";

const ZONE_NAMES = {
  zone_01:"Koramangala", zone_02:"HSR Layout", zone_03:"Indiranagar",
  zone_04:"BTM Layout",  zone_05:"Whitefield", zone_06:"Jayanagar",
  zone_07:"Marathahalli",zone_08:"Electronic City", zone_09:"Bannerghatta Rd",
  zone_10:"Rajajinagar", zone_11:"Malleshwaram", zone_12:"Yelahanka",
  zone_13:"JP Nagar",    zone_14:"Hebbal",      zone_15:"Sarjapur Rd",
  zone_16:"Bellandur",   zone_17:"Banashankari",zone_18:"MG Road",
  zone_19:"Cunningham Rd",zone_20:"Kengeri",
};

const STATUS_BADGE = {
  pending:  "badge-pending",
  approved: "badge-approved",
  executed: "badge-executed",
  resolved: "badge-resolved",
  rejected: "badge-rejected",
};

const TYPE_BADGE = {
  preemptive_redistribution: { label: "PROACTIVE", cls: "badge-proactive" },
  agent_redistribution:      { label: "REACTIVE",  cls: "badge-watch" },
};

function fmt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function ActionLog() {
  const [log, setLog] = useState([]);
  const { messages } = useWebSocket(WS);

  // Initial load
  useEffect(() => {
    fetch(`${API}/action_log`)
      .then((r) => r.json())
      .then(setLog)
      .catch(() => {});
  }, []);

  // Live updates
  useEffect(() => {
    const updates = messages.filter((m) => m.type === "action_log_update");
    if (updates.length === 0) return;
    updates.forEach((msg) => {
      const updated = msg.data;
      setLog((prev) => {
        const idx = prev.findIndex((a) => a.action_id === updated.action_id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = updated;
          return next;
        }
        return [updated, ...prev].slice(0, 50);
      });
    });
  }, [messages]);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div className="section-header">
        Action Log
        <span style={{ color: "var(--text-tertiary)", fontWeight: 400, textTransform: "none", letterSpacing: 0, fontSize: 11 }}>
          live · MongoDB change stream
        </span>
      </div>

      <div style={{ overflowY: "auto", flex: 1, padding: "8px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
        {log.length === 0 && (
          <div style={{ color: "var(--text-tertiary)", fontSize: 13, padding: "20px 0", textAlign: "center" }}>
            No actions yet
          </div>
        )}

        {log.map((action) => (
          <div
            key={action.action_id}
            className="card slide-in"
            style={{
              fontSize: 12,
              borderColor: action.type === "preemptive_redistribution" ? "#0c4a6e" : undefined,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
              <span style={{ fontWeight: 600, fontSize: 12.5 }}>
                {action.recommendation || action.type}
              </span>
              <div style={{ display: "flex", gap: 4, flexShrink: 0, marginLeft: 8 }}>
                {TYPE_BADGE[action.type] && (
                  <span className={`badge ${TYPE_BADGE[action.type].cls}`}>
                    {TYPE_BADGE[action.type].label}
                  </span>
                )}
                <span className={`badge ${STATUS_BADGE[action.status] || ""}`}>
                  {action.status}
                </span>
              </div>
            </div>

            <p style={{ color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: 6 }}>
              {action.reasoning?.slice(0, 160)}{action.reasoning?.length > 160 ? "…" : ""}
            </p>

            <div style={{ display: "flex", gap: 16, color: "var(--text-tertiary)", fontSize: 11 }}>
              <span>Created {fmt(action.created_at)}</span>
              {action.approved_at && <span>Approved {fmt(action.approved_at)}</span>}
              {action.executed_at && <span>Executed {fmt(action.executed_at)}</span>}
            </div>

            {(action.status === "executed" || action.status === "resolved") && (() => {
              // Use zone_changes if available — has exact before/after values
              if (action.zone_changes && action.zone_changes.length > 0) {
                return (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                    {action.zone_changes.map(({ zone_id, idle_before, idle_after, delta }) => (
                      <span key={zone_id} style={{
                        fontSize: 11, fontWeight: 600, padding: "2px 7px", borderRadius: 999,
                        background: delta > 0 ? "#14532d44" : "#7f1d1d44",
                        color: delta > 0 ? "#22c55e" : "#ef4444",
                      }}>
                        {delta > 0 ? `+${delta}` : delta} {ZONE_NAMES[zone_id] || zone_id}
                        <span style={{ fontWeight: 400, opacity: 0.8 }}> ({idle_before}→{idle_after})</span>
                      </span>
                    ))}
                  </div>
                );
              }
              // Fallback: compute from proposed_actions
              const deltas = {};
              (action.proposed_actions || []).forEach((m) => {
                if (m.type === "move_agent") {
                  deltas[m.from_zone] = (deltas[m.from_zone] || 0) - 1;
                  deltas[m.to_zone]   = (deltas[m.to_zone]   || 0) + 1;
                }
              });
              if (Object.keys(deltas).length === 0) return null;
              return (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                  {Object.entries(deltas).map(([zoneId, delta]) => (
                    <span key={zoneId} style={{
                      fontSize: 11, fontWeight: 600, padding: "2px 7px", borderRadius: 999,
                      background: delta > 0 ? "#14532d44" : "#7f1d1d44",
                      color: delta > 0 ? "#22c55e" : "#ef4444",
                    }}>
                      {delta > 0 ? `+${delta}` : delta} {ZONE_NAMES[zoneId] || zoneId}
                    </span>
                  ))}
                </div>
              );
            })()}

            {action.outcome && (
              <div style={{ marginTop: 8, padding: "6px 10px", background: "#14532d22", borderRadius: 6, border: "1px solid #14532d" }}>
                <span style={{ color: "var(--green)", fontWeight: 600 }}>
                  Resolved in {action.outcome.resolution_minutes} min
                </span>
                <span style={{ color: "var(--text-secondary)", marginLeft: 10 }}>
                  · {action.outcome.customer_minutes_saved} customer-minutes saved
                </span>
              </div>
            )}

            {action.modification && (
              <div style={{ marginTop: 6, fontSize: 11, color: "var(--amber)" }}>
                Manager note: {action.modification}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
