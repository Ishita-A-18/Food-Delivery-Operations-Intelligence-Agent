import { useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { CityMap } from "./components/CityMap";
import { ApprovalCard } from "./components/ApprovalCard";
import { ActionLog } from "./components/ActionLog";
import { ChatInput } from "./components/ChatInput";
import { AgentNotificationPanel } from "./components/AgentNotificationPanel";
import { IntroPage } from "./components/IntroPage";

const WS = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

export default function App() {
  const [showIntro, setShowIntro] = useState(true);
  const { connected } = useWebSocket(WS);

  if (showIntro) return <IntroPage onEnter={() => setShowIntro(false)} />;

  return (
    <div className="app-shell">
      {/* Top bar */}
      <header className="topbar">
        <span className={`ws-dot ${connected ? "connected" : ""}`} title={connected ? "Live" : "Disconnected"} />
        <h1>Delivery Ops Agent — Bangalore</h1>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-tertiary)" }}>
          {connected ? "● Live" : "○ Connecting…"}
        </span>
      </header>

      {/* Main grid */}
      <div className="main-grid">
        {/* Left — city map */}
        <div className="left-panel">
          <CityMap />
        </div>

        {/* Right — approval + log + notifications */}
        <div className="right-panel">
          <div className="panel-section" style={{ flexShrink: 0, maxHeight: "38%" }}>
            <ApprovalCard />
          </div>
          <div className="panel-section" style={{ flex: 1, minHeight: 0 }}>
            <ActionLog />
          </div>
          <div className="panel-section" style={{ flexShrink: 0, maxHeight: "28%" }}>
            <AgentNotificationPanel />
          </div>
        </div>
      </div>

      {/* Bottom bar — chat input */}
      <footer className="bottombar">
        <ChatInput />
      </footer>
    </div>
  );
}
