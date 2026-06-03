import { useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function ChatInput() {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    const goal = text.trim();
    if (!goal) return;

    setSending(true);
    setError(null);
    try {
      await fetch(`${API}/goal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      setText("");
      // Notify ApprovalCard to show a pending chat card immediately
      window.dispatchEvent(new CustomEvent("chatGoalPending", {
        detail: { goal, id: `chat_${Date.now()}` }
      }));
    } catch {
      setError("Failed to send — check connection");
      setTimeout(() => setError(null), 3000);
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
      {error && <div style={{ fontSize: 12, color: "#ef4444" }}>{error}</div>}
      <form onSubmit={submit} style={{ display: "flex", gap: 10, width: "100%", alignItems: "center" }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder='Ad-hoc goal — e.g. "Meghana Foods in HSR still overwhelmed"'
          disabled={sending}
          style={{
            flex: 1,
            padding: "9px 14px",
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            color: "var(--text-primary)",
            fontSize: 13,
            outline: "none",
          }}
        />
        <button
          type="submit"
          disabled={!text.trim() || sending}
          className="btn btn-approve"
          style={{ flexShrink: 0 }}
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </form>
    </div>
  );
}
