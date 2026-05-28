import { useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function ChatInput() {
  const [text, setText] = useState("");
  const [toast, setToast] = useState(null);
  const [sending, setSending] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    const goal = text.trim();
    if (!goal) return;

    setSending(true);
    try {
      await fetch(`${API}/goal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      setText("");
      setToast("Goal received — agent will process on next tick");
      setTimeout(() => setToast(null), 4000);
    } catch {
      setToast("Failed to send goal");
      setTimeout(() => setToast(null), 3000);
    } finally {
      setSending(false);
    }
  };

  return (
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

      {toast && (
        <div style={{
          position: "fixed", bottom: 80, left: "50%", transform: "translateX(-50%)",
          background: "var(--bg-card)", border: "1px solid var(--border)",
          padding: "10px 18px", borderRadius: 8, fontSize: 13,
          boxShadow: "0 8px 24px rgba(0,0,0,0.5)", zIndex: 100,
          animation: "slide-in 0.2s ease",
        }}>
          {toast}
        </div>
      )}
    </form>
  );
}
