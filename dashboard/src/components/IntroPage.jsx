import { useState, useEffect } from "react";

const LINES = [
  "Food delivery operations across a city don't fail gradually — they fail suddenly.",
  "A match ends, rain starts, a festival peaks. Demand spikes across multiple zones simultaneously.",
  "By the time a human notices, customers are already waiting.",
  "This agent monitors 20 delivery zones across Bangalore in real time.",
  "It detects imbalances, identifies the nearest available agents, and surfaces a recommended action.",
  "The operations manager reviews the reasoning and approves — or rejects — in one click.",
];

const TAGLINE = "Autonomous monitoring. Informed decisions. Human control.";

export function IntroPage({ onEnter }) {
  const [showHeader, setShowHeader] = useState(false);
  const [showLines, setShowLines] = useState(false);

  const [showButton, setShowButton] = useState(false);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const t0 = setTimeout(() => setShowHeader(true), 700);
    const t1 = setTimeout(() => setShowLines(true), 1900);
    const t2 = setTimeout(() => setShowButton(true), 3000);
    return () => { clearTimeout(t0); clearTimeout(t1); clearTimeout(t2); };
  }, []);

  function handleEnter() {
    setFading(true);
    setTimeout(onEnter, 700);
  }

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0f1117",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "flex-start",
      padding: "80px 24px 80px",
      opacity: fading ? 0 : 1,
      transition: "opacity 0.7s ease",
      overflowY: "auto",
    }}>
      {/* Header */}
      <div style={{
        textAlign: "center",
        marginBottom: 64,
        maxWidth: 680,
        opacity: showHeader ? 1 : 0,
        transform: showHeader ? "translateY(0)" : "translateY(12px)",
        transition: "opacity 0.7s ease, transform 0.7s ease",
      }}>
        <div style={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "2px",
          textTransform: "uppercase",
          color: "#3b82f6",
          marginBottom: 16,
          fontFamily: "Inter, system-ui, sans-serif",
        }}>
          AI Operations Agent
        </div>
        <h1 style={{
          fontSize: "clamp(26px, 4vw, 38px)",
          fontWeight: 700,
          color: "#e8eaf0",
          letterSpacing: "-0.5px",
          lineHeight: 1.25,
          margin: 0,
          fontFamily: "Inter, system-ui, sans-serif",
        }}>
          Delivery Operations Intelligence Agent
        </h1>
        <p style={{
          marginTop: 20,
          fontSize: 15,
          lineHeight: 1.7,
          color: "#8892a4",
          maxWidth: 560,
          marginLeft: "auto",
          marginRight: "auto",
          fontFamily: "Inter, system-ui, sans-serif",
        }}>
          A real-time operations assistant that monitors 20 delivery zones across Bangalore, detects demand imbalances, and proposes agent redistributions — always with a human in the loop.
        </p>
      </div>

      {/* Animated story lines — whole block fades in together */}
      <div style={{
        maxWidth: 620,
        width: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 20,
        marginBottom: 52,
        opacity: showLines ? 1 : 0,
        transform: showLines ? "translateY(0)" : "translateY(12px)",
        transition: "opacity 0.7s ease, transform 0.7s ease",
      }}>
        {LINES.map((line, i) => (
          <p
            key={i}
            style={{
              margin: 0,
              fontSize: 16,
              lineHeight: 1.65,
              fontFamily: "Inter, system-ui, sans-serif",
              color: i < 3 ? "#c8ccd6" : "#8892a4",
              borderLeft: i === 3 ? "2px solid #3b82f6" : "none",
              paddingLeft: i === 3 ? 16 : 0,
            }}
          >
            {line}
          </p>
        ))}
      </div>

      {/* Tagline */}
      <div style={{
        opacity: showButton ? 1 : 0,
        transform: showButton ? "translateY(0)" : "translateY(8px)",
        transition: "opacity 0.6s ease, transform 0.6s ease",
        marginBottom: 40,
        textAlign: "center",
      }}>
        <p style={{
          fontSize: 13,
          fontWeight: 600,
          letterSpacing: "0.5px",
          color: "#4e5a6e",
          fontFamily: "Inter, system-ui, sans-serif",
          margin: 0,
          textTransform: "uppercase",
        }}>
          {TAGLINE}
        </p>
      </div>

      {/* Enter button */}
      <div style={{
        opacity: showButton ? 1 : 0,
        transform: showButton ? "translateY(0)" : "translateY(8px)",
        transition: "opacity 0.5s ease, transform 0.5s ease",
      }}>
        <button
          onClick={handleEnter}
          style={{
            background: "#3b82f6",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "12px 32px",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "Inter, system-ui, sans-serif",
            letterSpacing: "0.2px",
            transition: "background 0.15s, transform 0.15s",
          }}
          onMouseEnter={(e) => { e.target.style.background = "#2563eb"; e.target.style.transform = "translateY(-1px)"; }}
          onMouseLeave={(e) => { e.target.style.background = "#3b82f6"; e.target.style.transform = "translateY(0)"; }}
        >
          Try it out →
        </button>
      </div>

      {/* Feature pills */}
      {showButton && (
        <div style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          marginTop: 32,
          justifyContent: "center",
          maxWidth: 500,
          opacity: showButton ? 1 : 0,
          transition: "opacity 0.6s ease 0.3s",
        }}>
          {["20 zones · Bangalore", "Gemini 2.5 Flash", "MongoDB Atlas", "Human approval loop", "Proximity-aware redistribution", "Proactive event prediction"].map((f) => (
            <span key={f} style={{
              padding: "4px 12px",
              borderRadius: 999,
              fontSize: 11,
              fontWeight: 500,
              color: "#8892a4",
              border: "1px solid #2a3550",
              background: "#161b27",
              fontFamily: "Inter, system-ui, sans-serif",
            }}>{f}</span>
          ))}
        </div>
      )}
    </div>
  );
}
