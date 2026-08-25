"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, AskAnswer } from "../lib/api";
import { BulletList } from "./BulletList";

/* The always-open line to the advisor.
 *
 * The Q&A endpoint never needed a brief — it rebuilds the book context cold if
 * there's no warm session — but the only way in was a textarea at the bottom of
 * a card called "Portfolio Brief", nineteen hundred pixels down the dashboard,
 * under a button that says "Generate brief". So it read as a follow-up feature
 * for a brief you hadn't run yet.
 *
 * This puts him on every page instead: one key, always there, no brief. The
 * thread survives navigation and reload so it reads as one continuing
 * conversation rather than a box that forgets you each time.
 */

const THREAD_KEY = "ps.advisor.dock.thread";
const OPEN_KEY = "ps.advisor.dock.open";
// Enough to scroll back through a working session; small enough that the stored
// thread can't grow without bound.
const KEEP_TURNS = 30;

interface Turn {
  q: string;
  a?: AskAnswer;
  err?: string;
  /** Local wall-clock of the question, for the thread's own timeline. */
  at?: string;
}

// Openers that are actually worth a Claude call — each one needs the whole book
// to answer, which is exactly what a one-line panel can't tell you.
const OPENERS = [
  "What needs my attention today?",
  "What's my biggest risk right now?",
  "Anything to do before the close?",
];

function load<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function AdvisorDock() {
  const [open, setOpen] = useState(false);
  const [thread, setThread] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [deep, setDeep] = useState(false);
  const [live, setLive] = useState<boolean | null>(null);
  const [why, setWhy] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [pinned, setPinned] = useState<Set<number>>(new Set());
  // Nothing is read from localStorage until after mount, so the server and the
  // first client paint agree.
  const [ready, setReady] = useState(false);

  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // localStorage paints instantly; the server's record is the truth and wins
    // as soon as it lands, so a thread started on the phone shows up here.
    setThread(load<Turn[]>(THREAD_KEY, []));
    // ?ask (or #ask) opens him directly — that's the landing spot for a push
    // notification tap, so "look at this" can go straight into a conversation.
    const deepLink =
      typeof window !== "undefined" &&
      (new URLSearchParams(window.location.search).has("ask") ||
        window.location.hash === "#ask");
    setOpen(deepLink || load<boolean>(OPEN_KEY, false));
    setReady(true);
    api.advisorChat("portfolio").then(({ turns }) => {
      if (!turns.length) return;
      setThread(
        turns.map((t) => ({
          q: t.q,
          at: t.ts.slice(11, 16),
          a: { engine: "claude", answer: t.a, points: t.points, generated_at: t.ts },
        }))
      );
    });
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(THREAD_KEY, JSON.stringify(thread.slice(-KEEP_TURNS)));
    } catch {
      /* a full quota shouldn't break the chat */
    }
  }, [thread, ready]);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(OPEN_KEY, JSON.stringify(open));
    } catch {
      /* ignore */
    }
  }, [open, ready]);

  // Is he actually reachable? Checked on mount and whenever the dock is opened,
  // so the indicator reflects now rather than page-load time.
  // Fails soft on purpose: an unreachable backend is a status to display, not
  // an error to throw at the user mid-conversation.
  const probe = useCallback(() => {
    api
      .health()
      .then((h) => {
        setLive(h.status === "ok" && h.advisor_enabled);
        // A block is not an outage, and the two blocks have OPPOSITE fixes:
        // a quota resets on its own, an expired login never does. Saying
        // "unreachable" for either sent us hunting a healthy CLI twice, so the
        // dot now carries the reason AND the thing to do about it.
        const e = h.advisor_error;
        setWhy(
          e?.reason === "auth" ? "signed out — run /login"
          : e?.reason === "usage_limit" ? "usage limit — resets on its own"
          : e?.reason === "blocked" ? "CLI refused the request"
          : e?.detail ? e.detail.slice(0, 80)
          : null,
        );
        setHint(e?.hint ?? null);
      })
      .catch(() => {
        setLive(false);
        setWhy(null);
        setHint(null);
      });
  }, []);
  useEffect(probe, [probe]);

  // Cmd/Ctrl+K from anywhere. Esc closes — unless a question is in flight, in
  // which case closing would orphan the answer, so the panel stays put.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
        return;
      }
      if (e.key === "Escape" && open && !busy) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy]);

  useEffect(() => {
    if (!open) return;
    probe();
    // Focus the field, not the panel — opening it should mean you can type.
    const id = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [open, probe]);

  // Follow the conversation as it grows.
  useEffect(() => {
    boxRef.current?.scrollTo({ top: boxRef.current.scrollHeight, behavior: "smooth" });
  }, [thread, busy]);

  const ask = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy) return;
      setInput("");
      setBusy(true);
      const at = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      setThread((t) => [...t, { q, at }]);
      try {
        const a = await api.askAdvisor("portfolio", undefined, q, deep);
        setThread((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a } : x)));
      } catch (e: any) {
        setThread((t) =>
          t.map((x, i) =>
            i === t.length - 1 ? { ...x, err: e?.message || "The advisor didn't answer." } : x
          )
        );
        // A failed ask is the most likely moment for him to have gone away.
        probe();
      } finally {
        setBusy(false);
      }
    },
    [busy, deep, probe]
  );

  if (!ready) return null;

  if (!open) {
    return (
      <button className="adock-launch" onClick={() => setOpen(true)} title="Ask your advisor (Ctrl+K)">
        <span className={`adock-dot${live === false ? " off" : ""}`} />
        <span className="adock-launch-label">Ask your advisor</span>
        <span className="adock-kbd">CTRL K</span>
      </button>
    );
  }

  return (
    <div className="adock" role="dialog" aria-label="Advisor">
      <div className="adock-head">
        <span className={`adock-dot${live === false ? " off" : ""}`} />
        <span className="adock-who">Advisor</span>
        <span className="adock-state">
          {live === false ? "unreachable" : live == null ? "checking" : why ? why : "on"}
        </span>
        <div className="adock-head-right">
          <label className="adock-deep" title="Let him search the web for live news and sentiment (slower)">
            <input
              type="checkbox"
              checked={deep}
              onChange={(e) => setDeep(e.target.checked)}
              disabled={busy}
            />
            Deep
          </label>
          {thread.length > 0 && (
            <button
              className="adock-icon"
              title="Clear this thread"
              onClick={() => {
                setThread([]);
                setPinned(new Set());
                // Forget it on the server too, or it returns on next load and
                // still feeds his recap.
                api.clearAdvisorChat("portfolio").catch(() => {});
              }}
              disabled={busy}
            >
              Clear
            </button>
          )}
          <button className="adock-icon" title="Close (Esc)" onClick={() => setOpen(false)}>
            ×
          </button>
        </div>
      </div>

      {/* The fix belongs where the failure is felt. Twice now a blocked CLI
          read as an outage and cost an hour of hunting a healthy binary — a
          status with no next step does that. */}
      {hint && (
        <div className={`adock-fix${why?.startsWith("signed out") ? " act" : ""}`}>
          {hint}
        </div>
      )}

      <div className="adock-body" ref={boxRef}>
        {thread.length === 0 && (
          <div className="adock-empty">
            <p>
              He has your whole book — positions, cost basis, cash, your standing
              calls — in front of him. No brief needed.
            </p>
            <div className="adock-openers">
              {OPENERS.map((o) => (
                <button key={o} className="adock-opener" onClick={() => ask(o)}>
                  {o}
                </button>
              ))}
            </div>
          </div>
        )}

        {thread.map((t, i) => (
          <div key={i} className="adock-turn">
            <div className="adock-q">
              {t.q}
              {t.at && <span className="adock-at">{t.at}</span>}
            </div>
            {t.a ? (
              <div className="adock-a">
                <p>{t.a.answer}</p>
                <BulletList items={t.a.points} kind="insight" />
                <button
                  className={`pin-btn${pinned.has(i) ? " pinned" : ""}`}
                  title="Pin this to your action list"
                  onClick={async () => {
                    if (pinned.has(i)) return;
                    await api.addPin({ source: "ask", text: t.a!.answer, points: t.a!.points });
                    setPinned((p) => new Set(p).add(i));
                  }}
                >
                  {pinned.has(i) ? "Pinned" : "Pin"}
                </button>
              </div>
            ) : t.err ? (
              <div className="adock-err">{t.err}</div>
            ) : (
              <div className="adock-a">
                <p className="mut">
                  {deep ? "Researching the web, then thinking… (1-3 min)" : "Thinking… (~10-30s)"}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="adock-input">
        <textarea
          ref={inputRef}
          value={input}
          rows={1}
          placeholder="Ask him anything about your book…"
          disabled={busy}
          onChange={(e) => {
            setInput(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(input);
            }
          }}
        />
        <button className="btn" onClick={() => ask(input)} disabled={busy || !input.trim()}>
          {busy ? "…" : "Ask"}
        </button>
      </div>
    </div>
  );
}
