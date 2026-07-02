"use client";
import { useState } from "react";
import { api, AskAnswer } from "../lib/api";
import { BulletList } from "./BulletList";

interface QA {
  q: string;
  a?: AskAnswer;
  err?: string;
}

// Follow-up Q&A thread under an advisor note. The backend resumes the same
// Claude session, so questions like "is that exit short-term or long-term?"
// are answered with the original brief and data still in context.
export function AdvisorChat({
  kind,
  symbol,
  deep = false,
}: {
  kind: "portfolio" | "stock" | "breakout";
  symbol?: string;
  deep?: boolean;
}) {
  const [thread, setThread] = useState<QA[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pinnedIdx, setPinnedIdx] = useState<Set<number>>(new Set());

  async function send() {
    const q = input.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setThread((t) => [...t, { q }]);
    try {
      const a = await api.askAdvisor(kind, symbol, q, deep);
      setThread((t) => t.map((item, i) => (i === t.length - 1 ? { ...item, a } : item)));
    } catch (e: any) {
      setThread((t) =>
        t.map((item, i) => (i === t.length - 1 ? { ...item, err: e.message || "Ask failed" } : item))
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      {thread.map((item, i) => (
        <div key={i} className="chat-item">
          <div className="chat-q">{item.q}</div>
          {item.a ? (
            <div className="chat-a">
              <p>
                {item.a.answer}{" "}
                <button
                  className={`pin-btn${pinnedIdx.has(i) ? " pinned" : ""}`}
                  title="Pin this answer to your action list"
                  onClick={async () => {
                    if (pinnedIdx.has(i)) return;
                    await api.addPin({
                      symbol,
                      source: "ask",
                      text: item.a!.answer,
                      points: item.a!.points,
                    });
                    setPinnedIdx((prev) => new Set(prev).add(i));
                  }}
                >
                  {pinnedIdx.has(i) ? "✓ Pinned" : "Pin"}
                </button>
              </p>
              <BulletList items={item.a.points} kind="insight" />
            </div>
          ) : item.err ? (
            <div className="err">{item.err}</div>
          ) : (
            <div className="chat-a">
              <p className="mut">{deep ? "Researching the web + thinking… (1-3 min)" : "Thinking… (~10-30s)"}</p>
            </div>
          )}
        </div>
      ))}
      <div className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={
            kind === "portfolio"
              ? 'Ask or tell the advisor anything — e.g. "I just sold half my IREN and added to MU"'
              : 'Ask a follow-up — e.g. "Is that exit short-term or long-term guidance?"'
          }
          disabled={busy}
        />
        <button className="btn" onClick={send} disabled={busy || !input.trim()}>
          {busy ? "…" : "Ask"}
        </button>
      </div>
    </div>
  );
}
