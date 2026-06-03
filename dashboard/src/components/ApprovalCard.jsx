import { useState, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS  = import.meta.env.VITE_WS_URL  || "ws://localhost:8000/ws";

export function ApprovalCard() {
  const [pending, setPending] = useState([]);
  const [chatGoals, setChatGoals] = useState([]);
  const [modifyId, setModifyId] = useState(null);
  const [modifyText, setModifyText] = useState("");
  const [loading, setLoading] = useState({});
  const { messages } = useWebSocket(WS);

  // Load existing pending actions on mount
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

  // Listen for chat goals from ChatInput — show immediately as pending card
  useEffect(() => {
    const handler = (e) => setChatGoals((prev) => [...prev, e.detail]);
    window.addEventListener("chatGoalPending", handler);
    return () => window.removeEventListener("chatGoalPending", handler);
  }, []);

  // New pending actions via WebSocket — when Gemini responds to a chat goal, remove oldest chat card
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
    // Remove oldest chat goal card — Gemini just turned it into a real card
    setChatGoals((prev) => prev.slice(incoming.length));
  }, [messages]);

  // Remove cards when WebSocket confirms executed or rejected
  useEffect(() => {
    const done = messages.filter(
      (m) => m.type === "action_log_update" &&
             (m.data.status === "executed" || m.data.status === "rejected")
    );
    if (done.length === 0) return;
    const doneIds = new Set(done.map((m) => m.data.action_id));
    setPending((p) => p.filter((a) => !doneIds.has(a.action_id)));
  }, [messages]);

  const act = async (action_id, endpoint, body = {}) => {
    setLoading((p) => ({ ...p, [action_id]: true }));
    try {
      await fetch(`${API}/${endpoint}/${action_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (endpoint === "approve") {
        setPending((p) => p.map((a) =>
          a.action_id === action_id ? { ...a, _executing: true } : a
        ));
      } else {
        setPending((p) => p.filter((a) => a.action_id !== action_id));
      }
    } finally {
      setLoading((p) => ({ ...p, [action_id]: false }));
      setModifyId(null);
      setModifyText("");
    }
  };

  const totalCount = pending.length + chatGoals.length;

  if (totalCount === 0) {
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
          {totalCount}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "10px 12px" }}>

        {/* Chat goal pending cards */}
        {chatGoals.map((cg) => (
          <div key={cg.id} className="card slide-in" style={{ borderColor: "#1e3a5f" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>Manager goal received</span>
              <span className="badge badge-proactive">CHAT</span>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: 12, lineHeight: 1.6, marginBottom: 6 }}>
              "{cg.goal}"
            </p>
            <div style={{ fontSize: 11, color: "#f59e0b" }}>
              ⟳ Agent processing — proposal will appear within 60s
            </div>
            <button
              onClick={() => setChatGoals((prev) => prev.filter((g) => g.id !== cg.id))}
              style={{ marginTop: 8, background: "none", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text-tertiary)", cursor: "pointer", fontSize: 11, padding: "3px 8px" }}
            >
              Dismiss
            </button>
          </div>
        ))}

        {/* Approval cards from Gemini */}
        {pending.map((action) => (
          <div key={action.action_id} className="card slide-in" style={{ borderColor: action._executing ? "#78350f55" : "#7f1d1d55" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{action.recommendation}</span>
              <span
                className={`badge ${action._executing ? "badge-proactive" : action.type === "preemptive_redistribution" ? "badge-proactive" : "badge-critical"}`}
                style={{ flexShrink: 0, marginLeft: 8 }}
              >
                {action._executing ? "EXECUTING" : action.type === "preemptive_redistribution" ? "PROACTIVE" : "CRITICAL"}
              </span>
            </div>

            <p style={{ color: "var(--text-secondary)", fontSize: 12, lineHeight: 1.6, marginBottom: 10 }}>
              {action.reasoning}
            </p>

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

            {!action._executing && modifyId === action.action_id && (
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

            {action._executing ? (
              <div style={{ fontSize: 12, color: "#f59e0b", fontWeight: 600, padding: "4px 0" }}>
                ⟳ Executing — agents being redistributed…
              </div>
            ) : (
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
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
