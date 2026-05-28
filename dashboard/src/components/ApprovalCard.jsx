import { useState, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS  = import.meta.env.VITE_WS_URL  || "ws://localhost:8000/ws";

export function ApprovalCard() {
  const [pending, setPending] = useState([]);
  const [modifyId, setModifyId] = useState(null);
  const [modifyText, setModifyText] = useState("");
  const [loading, setLoading] = useState({});
  const { messages } = useWebSocket(WS);

  const fetchPending = () => {
    fetch(`${API}/pending_actions`)
      .then((r) => r.json())
      .then(setPending)
      .catch(() => {});
  };

  useEffect(() => {
    fetchPending();
    const id = setInterval(fetchPending, 5000);
    return () => clearInterval(id);
  }, []);

  // New pending cards arrive instantly via WebSocket — no need to wait for next poll
  useEffect(() => {
    const incoming = messages
      .filter((m) => m.type === "action_log_update" && m.data.status === "pending")
      .map((m) => m.data);
    if (incoming.length === 0) return;
    setPending((prev) => {
      const map = new Map(prev.map((a) => [a.action_id, a]));
      for (const a of incoming) map.set(a.action_id, a);
      return Array.from(map.values());
    });
  }, [messages]);

  const act = async (action_id, endpoint, body = {}) => {
    setLoading((p) => ({ ...p, [action_id]: true }));
    try {
      await fetch(`${API}/${endpoint}/${action_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setPending((p) => p.filter((a) => a.action_id !== action_id));
    } finally {
      setLoading((p) => ({ ...p, [action_id]: false }));
      setModifyId(null);
      setModifyText("");
    }
  };

  if (pending.length === 0) {
    return (
      <div style={{ padding: "14px 16px" }}>
        <div className="section-header" style={{ padding: 0, marginBottom: 10 }}>Pending Approval</div>
        <div style={{ color: "var(--text-tertiary)", fontSize: 13, padding: "20px 0", textAlign: "center" }}>
          No pending recommendations
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: "0 0 8px" }}>
      <div className="section-header">
        Pending Approval
        <span style={{ background: "#7f1d1d", color: "#ef4444", borderRadius: 999, padding: "1px 7px", fontSize: 11, fontWeight: 700 }}>
          {pending.length}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "10px 12px" }}>
        {pending.map((action) => (
          <div key={action.action_id} className="card slide-in" style={{ borderColor: "#7f1d1d55" }}>
            {/* Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{action.recommendation}</span>
              <span
                className={`badge ${action.type === "preemptive_redistribution" ? "badge-proactive" : "badge-critical"}`}
                style={{ flexShrink: 0, marginLeft: 8 }}
              >
                {action.type === "preemptive_redistribution" ? "PROACTIVE" : "CRITICAL"}
              </span>
            </div>

            {/* Reasoning */}
            <p style={{ color: "var(--text-secondary)", fontSize: 12, lineHeight: 1.6, marginBottom: 10 }}>
              {action.reasoning}
            </p>

            {/* Proposed moves list */}
            <div style={{ marginBottom: 12 }}>
              {(action.proposed_actions || []).slice(0, 5).map((move, i) => (
                <div key={i} style={{ display: "flex", gap: 8, fontSize: 11, color: "var(--text-tertiary)", marginBottom: 3 }}>
                  <span>→</span>
                  {move.type === "move_agent" && (
                    <span>{move.agent_id}: {move.from_zone} → {move.to_zone}</span>
                  )}
                  {move.type === "pause_restaurant" && (
                    <span>Pause {move.restaurant_id} ({move.reason})</span>
                  )}
                </div>
              ))}
              {(action.proposed_actions || []).length > 5 && (
                <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                  +{action.proposed_actions.length - 5} more moves
                </div>
              )}
            </div>

            {/* Modify input */}
            {modifyId === action.action_id && (
              <input
                autoFocus
                value={modifyText}
                onChange={(e) => setModifyText(e.target.value)}
                placeholder="Exception note (e.g. skip surge pricing)…"
                style={{
                  width: "100%", marginBottom: 10, padding: "7px 10px",
                  background: "var(--bg-secondary)", border: "1px solid var(--border)",
                  borderRadius: 6, color: "var(--text-primary)", fontSize: 12, outline: "none",
                }}
              />
            )}

            {/* Action buttons */}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-approve"
                disabled={loading[action.action_id]}
                onClick={() => act(action.action_id, "approve", { modification: modifyText || null })}
              >
                Approve
              </button>
              <button
                className="btn btn-modify"
                onClick={() => setModifyId(modifyId === action.action_id ? null : action.action_id)}
              >
                Modify
              </button>
              <button
                className="btn btn-reject"
                disabled={loading[action.action_id]}
                onClick={() => act(action.action_id, "reject")}
              >
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
