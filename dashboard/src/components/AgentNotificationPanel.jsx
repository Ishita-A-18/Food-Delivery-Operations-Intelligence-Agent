import { useState, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

const WS = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

function fmt(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function AgentNotificationPanel() {
  const { messages } = useWebSocket(WS);
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    const pings = messages.filter((m) => m.type === "agent_notification");
    if (pings.length === 0) return;
    setNotifications((prev) => {
      // Merge by notification_id so acknowledged updates overwrite sent ones
      const map = new Map(prev.map((n) => [n.notification_id, n]));
      for (const p of pings) map.set(p.data.notification_id, p.data);
      return Array.from(map.values()).slice(0, 20);
    });
  }, [messages]);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div className="section-header">
        Agent Notifications
        {notifications.filter((n) => n.status === "sent").length > 0 && (
          <span style={{ background: "#78350f", color: "#f59e0b", borderRadius: 999, padding: "1px 7px", fontSize: 11, fontWeight: 700 }}>
            {notifications.filter((n) => n.status === "sent").length} pending
          </span>
        )}
      </div>

      <div style={{ overflowY: "auto", padding: "8px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
        {notifications.length === 0 && (
          <div style={{ color: "var(--text-tertiary)", fontSize: 13, padding: "16px 0", textAlign: "center" }}>
            No notifications yet
          </div>
        )}

        {notifications.map((n, i) => (
          <div
            key={n.notification_id || i}
            className="slide-in"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "9px 12px",
              borderRadius: 8,
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              fontSize: 12,
            }}
          >
            {/* Status dot */}
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                flexShrink: 0,
                background: n.status === "acknowledged" ? "#22c55e" : "#f59e0b",
                transition: "background 0.4s",
              }}
            />

            {/* Agent ID */}
            <span style={{ fontWeight: 600, minWidth: 76, color: "var(--text-primary)" }}>
              {n.agent_id}
            </span>

            {/* Message */}
            <span style={{ flex: 1, color: "var(--text-secondary)" }}>{n.message}</span>

            {/* Time */}
            <span style={{ color: "var(--text-tertiary)", fontSize: 11, flexShrink: 0 }}>
              {fmt(n.acknowledged_at || n.sent_at)}
            </span>

            {/* Ack badge */}
            {n.status === "acknowledged" ? (
              <span style={{ fontSize: 10, color: "#22c55e", fontWeight: 600 }}>ACK</span>
            ) : (
              <span style={{ fontSize: 10, color: "#f59e0b", fontWeight: 600 }}>SENT</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
