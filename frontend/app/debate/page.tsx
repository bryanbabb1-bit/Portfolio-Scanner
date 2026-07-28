"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, Debate } from "../../lib/api";
import { DebatePentagon } from "../../components/DebatePentagon";
import {
  DisplayHead,
  SheetRule,
  SpecEmpty,
  SpecHeader,
  SpecPanel,
  TelemetryStrip,
} from "../../components/blueprint";
import { money } from "../../components/format";
import "./debate.css";

/* Agent Debate — sheet 03/08. Five specialists argue, a judge rules.
   Strictly on demand: convening costs six model calls, so nothing here fires
   on mount except reading what the desk already decided. */

const PROCESS = [
  { n: "01", t: "Debate", d: "Five agents argue their corner over one shared evidence pack." },
  { n: "02", t: "Score", d: "Each states a position and how strongly the data backs it." },
  { n: "03", t: "Rule", d: "The judge weighs evidence over rhetoric and overrules the losers." },
  { n: "04", t: "Size", d: "The risk desk sets the position size — never the model." },
];

export default function DebatePage() {
  const [symbol, setSymbol] = useState("");
  const [d, setD] = useState<Debate | null>(null);
  const [recent, setRecent] = useState<Debate[]>([]);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.debates().then((r) => setRecent(r.results)).catch(() => {});

    // Deep link: /debate?symbol=NVDA opens the standing ruling. It never
    // convenes on its own — arriving at a URL must not spend six model calls.
    const q = new URLSearchParams(window.location.search).get("symbol");
    if (q) {
      const sym = q.toUpperCase();
      setSymbol(sym);
      api
        .debate(sym)
        .then((existing) => existing && setD(existing))
        .catch(() => {});
    }
    return () => {
      if (poll.current) clearInterval(poll.current);
    };
  }, []);

  const convene = async (sym: string, force = false) => {
    const s = sym.trim().toUpperCase();
    if (!s || running) return;
    setErr(null);
    setRunning(true);
    setD(null);
    try {
      const start = await api.startDebate(s, force);
      if (start.result) {
        setD(start.result);
        setRunning(false);
        return;
      }
      if (!start.job_id) throw new Error("The desk did not start");
      poll.current = setInterval(async () => {
        try {
          const j = await api.debateJob(start.job_id!);
          if (j.status === "done" && j.result) {
            if (poll.current) clearInterval(poll.current);
            setD(j.result);
            setRunning(false);
            api.debates().then((r) => setRecent(r.results)).catch(() => {});
          } else if (j.status === "error") {
            if (poll.current) clearInterval(poll.current);
            setErr(j.error || "The debate failed");
            setRunning(false);
          }
        } catch {
          /* a dropped poll is not fatal — the next one will land */
        }
      }, 4000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRunning(false);
    }
  };

  const load = async (sym: string) => {
    setErr(null);
    const existing = await api.debate(sym).catch(() => null);
    if (existing) setD(existing);
    else convene(sym);
  };

  return (
    <>
      <SpecHeader system="AGENT DEBATE" version="2.0" />
      <SheetRule mark="03 / 08" />

      <div className="deb-top">
        <DisplayHead
          line1="Then the"
          line2="agents debate."
          sub={
            <>
              Every idea gets challenged
              <br />
              <span className="hot">before it reaches you.</span>
            </>
          }
        />

        <SpecPanel
          title="Debate Status"
          aux={d ? `As of ${d.as_of.slice(0, 16)}` : "Idle"}
          className="deb-status"
        >
          <form
            className="deb-form"
            onSubmit={(e) => {
              e.preventDefault();
              convene(symbol);
            }}
          >
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="TICKER"
              aria-label="Ticker to debate"
              maxLength={8}
            />
            <button className="btn" disabled={running || !symbol.trim()}>
              {running ? "In session…" : "Convene"}
            </button>
          </form>
          <dl className="deb-rows">
            <Row k="Agents connected" v={d ? `${d.agents_reporting} of 5` : "5 idle"} />
            <Row
              k="Tally"
              v={
                d
                  ? `${d.tally.bullish} bull · ${d.tally.bearish} bear · ${d.tally.neutral} neutral`
                  : "—"
              }
            />
            <Row k="Cost per session" v="6 model calls" />
          </dl>
          <p className="deb-cost">
            On demand only — the desk never convenes on a page load or a poll.
          </p>
        </SpecPanel>
      </div>

      {err && <div className="err">{err}</div>}

      <DebatePentagon agents={d?.agents ?? []} running={running} />

      {running && (
        <p className="deb-running">
          Five agents arguing, then the judge — this takes about a minute.
        </p>
      )}

      {d && (
        <>
          {/* the ruling */}
          <SpecPanel
            title="The Ruling"
            aux={`${d.symbol} · ${money(d.price)}`}
            className={`deb-verdict ${d.verdict === "APPROVE" ? "approve" : "reject"}`}
          >
            <div className="dv-head">
              <span className="dv-badge">{d.verdict ?? "NO RULING"}</span>
              <span className="dv-action">{d.action}</span>
              <span className="dv-score">
                {d.score}
                <i>/100</i>
              </span>
            </div>
            <p className="dv-headline">{d.headline}</p>

            {d.error && <p className="dv-error">{d.error}</p>}

            <div className="dv-cols">
              <div>
                <h4 className="advisor-sec-h">Why this won</h4>
                <ul className="bullets">
                  {d.rationale.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="advisor-sec-h">What would make it wrong</h4>
                <ul className="bullets risk">
                  {d.dissent.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="dv-levels">
              <Level k="Entry" v={d.entry || "—"} />
              <Level k="Target" v={d.target || "—"} />
              <Level k="Stop" v={d.stop || "—"} />
              <Level
                k="Size (desk)"
                v={d.sizing.dollars ? money(d.sizing.dollars, 0) : "—"}
              />
            </div>
            <p className="dv-sizing">{d.sizing.note}</p>
          </SpecPanel>

          {/* the transcript */}
          <div className="section-title" style={{ marginTop: 26 }}>
            The transcript
          </div>
          <div className="deb-grid">
            {d.agents.map((a) => (
              <SpecPanel
                key={a.key}
                title={a.name}
                aux={`R${a.round}`}
                className={`deb-agent ${a.ok ? a.position.toLowerCase() : "silent"}`}
              >
                <div className="da-head">
                  <span className="da-pos">{a.ok ? a.position : "NO RESPONSE"}</span>
                  {a.ok && (
                    <span className="da-conf">
                      <i>confidence</i> {a.confidence}
                    </span>
                  )}
                </div>
                {a.ok ? (
                  <>
                    <ul className="bullets">
                      {a.points.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                    {a.strongest && <p className="da-strong">{a.strongest}</p>}
                  </>
                ) : (
                  <p className="da-silent">
                    This agent did not report — its view is missing from the tally.
                  </p>
                )}
              </SpecPanel>
            ))}
          </div>

          <button
            className="btn ghost deb-refresh"
            onClick={() => convene(d.symbol, true)}
            disabled={running}
          >
            Re-convene on {d.symbol}
          </button>
        </>
      )}

      {!d && !running && (
        <SpecEmpty>
          <b>The desk is idle.</b> Enter a ticker above to convene a debate, or
          reopen one of the rulings below. Nothing is computed until you ask —
          a session costs six model calls.
        </SpecEmpty>
      )}

      {/* the process strip */}
      <div className="section-title" style={{ marginTop: 26 }}>
        Debate process
      </div>
      <div className="deb-process">
        {PROCESS.map((p) => (
          <SpecPanel key={p.n} plus={false}>
            <span className="step-num">{p.n}</span>
            <h3 className="dp-title">{p.t}</h3>
            <div className="dh-rule dp-rule" />
            <p className="dp-body">{p.d}</p>
          </SpecPanel>
        ))}
      </div>

      {recent.length > 0 && (
        <>
          <div className="section-title" style={{ marginTop: 26 }}>
            Prior rulings
          </div>
          <SpecPanel plus={false} className="deb-recent">
            {recent.map((r) => (
              <button
                key={r.symbol}
                className={`dr-row ${r.verdict === "APPROVE" ? "approve" : "reject"}`}
                onClick={() => load(r.symbol)}
              >
                <span className="drr-sym">{r.symbol}</span>
                <span className="drr-verdict">{r.verdict}</span>
                <span className="drr-action">{r.action}</span>
                <span className="drr-headline">{r.headline}</span>
                <span className="drr-score">{r.score}</span>
              </button>
            ))}
          </SpecPanel>
        </>
      )}

      <TelemetryStrip
        left={[
          ["Agents", "5"],
          ["Rounds", "2"],
          ["Judge", "1"],
        ]}
        right={[
          ["Tier", "STANDARD"],
          ["Judge", "BEST"],
          ["Cache", "6H"],
        ]}
        line1="Five agents. One goal."
        line2="Consistent edge."
      />
    </>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="rs-row">
      <dt>{k}</dt>
      <dd>{v}</dd>
    </div>
  );
}

function Level({ k, v }: { k: string; v: string }) {
  return (
    <div className="dv-level">
      <span className="label">{k}</span>
      <b>{v}</b>
    </div>
  );
}
