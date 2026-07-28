"use client";
import { useEffect, useRef, useState } from "react";
import { api, CleanSheet } from "../../lib/api";
import {
  DisplayHead,
  SheetRule,
  SpecEmpty,
  SpecHeader,
  SpecPanel,
  StatTile,
  TelemetryStrip,
} from "../../components/blueprint";
import { money } from "../../components/format";
import "./cleansheet.css";

/* Clean Sheet — sheet 07/08.
   The book the desk builds knowing nothing about what you own, then the diff.
   Answers the one question you cannot ask the advisor directly: does it
   recommend your holdings because it believes in them, or because they are
   what it was shown. */

export default function CleanSheetPage() {
  const [d, setD] = useState<CleanSheet | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api
      .cleansheet()
      .then(setD)
      .catch(() => {})
      .finally(() => setLoaded(true));
    return () => {
      if (poll.current) clearInterval(poll.current);
    };
  }, []);

  const run = async () => {
    if (running) return;
    setErr(null);
    setRunning(true);
    try {
      const start = await api.startCleansheet();
      if (!start.job_id) throw new Error("The desk did not start");
      poll.current = setInterval(async () => {
        try {
          const j = await api.cleansheetJob(start.job_id!);
          if (j.status === "done" && j.result) {
            if (poll.current) clearInterval(poll.current);
            setD(j.result);
            setRunning(false);
          } else if (j.status === "error") {
            if (poll.current) clearInterval(poll.current);
            setErr(j.error || "The build failed");
            setRunning(false);
          }
        } catch {
          /* a dropped poll is not fatal */
        }
      }, 4000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRunning(false);
    }
  };

  const diff = d?.diff;
  const held = new Set(diff?.held_picks ?? []);

  return (
    <>
      <SpecHeader system="CLEAN SHEET" version="2.0" />
      <SheetRule mark="07 / 08" />

      <div className="cs-top">
        <DisplayHead
          line1="Built from"
          line2="a blank sheet."
          tone="hot"
          sub={
            <>
              What the desk would own
              <br />
              <span className="hot">if it had never seen your book.</span>
            </>
          }
        />

        <SpecPanel
          title="Build Status"
          aux={d?.as_of ? d.as_of.slice(0, 16) : "Never run"}
          className="cs-status"
        >
          <dl className="rs-rows">
            <Row k="Method" v="Blind construction" />
            <Row k="Overlap by weight" v={diff ? `${diff.overlap_pct}%` : "—"} />
            <Row k="Cost" v="1 model call · cached 24h" />
          </dl>
          <button className="btn cs-run" onClick={run} disabled={running}>
            {running ? "Building…" : d ? "Rebuild from scratch" : "Build the clean sheet"}
          </button>
          {d?.method && <p className="cs-method">{d.method}</p>}
        </SpecPanel>
      </div>

      {err && <div className="err">{err}</div>}
      {d?.error && <div className="err">{d.error}</div>}

      {!d && loaded && !running && (
        <SpecEmpty>
          <b>No clean sheet on record.</b> The desk has never been asked to
          build without seeing your positions. Run it and the comparison below
          becomes the honest test of whether your concentration is a conviction
          or an anchor.
        </SpecEmpty>
      )}

      {running && !d && (
        <p className="cs-running">Scanning the whole market, then building blind…</p>
      )}

      {d && diff && (
        <>
          <SpecPanel
            title="The Verdict"
            aux={d.equity ? money(d.equity, 0) : ""}
            className={`cs-verdict ${d.verdict?.toLowerCase() ?? ""}`}
          >
            <div className="csv-head">
              <span className="csv-badge">{d.verdict}</span>
              <span className="csv-num">
                {diff.overlap_pct}
                <i>% overlap</i>
              </span>
            </div>
            <p className="csv-headline">{d.headline}</p>
            {d.thesis && <p className="csv-thesis">{d.thesis}</p>}
          </SpecPanel>

          <div className="tile-row cs-tiles">
            <StatTile
              label="Overlap by weight"
              value={`${diff.overlap_pct}%`}
              tone={diff.overlap_pct >= 60 ? "pos" : "neg"}
              foot="Of the blind book you already own"
            />
            <StatTile
              label="Overlap by name"
              value={`${diff.name_overlap_pct}%`}
              foot={`${diff.held_picks.length} of ${diff.held_picks.length + diff.new_picks.length} picks`}
            />
            <StatTile
              label="Blind spots"
              value={`${diff.blind_spots.length}`}
              tone={diff.blind_spots.length ? "neg" : "pos"}
              foot="Sleeves wanted, nothing held"
            />
            <StatTile
              label="Biggest cut"
              value={
                diff.overweight.length
                  ? `${diff.overweight[0].delta.toFixed(0)}pt`
                  : "—"
              }
              tone={diff.overweight.length ? "neg" : "pos"}
              foot={diff.overweight[0]?.theme ?? "Nothing overweight"}
            />
          </div>

          {/* the allocation diff */}
          <SpecPanel title="Target vs Today" aux="by theme" className="cs-diff">
            <div className="csd-row csd-head">
              <span>Theme</span>
              <span>Blind build</span>
              <span>Your book</span>
              <span className="csd-barh">Gap</span>
              <span>Delta</span>
            </div>
            {diff.themes.map((t) => (
              <div key={t.theme} className={`csd-row ${t.current_pct === 0 && t.target_pct >= 5 ? "gap" : ""}`}>
                <span className="csd-theme">{t.theme}</span>
                <span className="csd-n">{t.target_pct.toFixed(1)}%</span>
                <span className="csd-n">{t.current_pct.toFixed(1)}%</span>
                <span className="csd-bar">
                  <i className="csd-axis" />
                  <i
                    className={`csd-fill ${t.delta >= 0 ? "up" : "down"}`}
                    style={{
                      width: `${Math.min(50, Math.abs(t.delta) / 2)}%`,
                      [t.delta >= 0 ? "left" : "right"]: "50%",
                    }}
                  />
                </span>
                <span className={`csd-delta ${t.delta >= 0 ? "pos" : "neg"}`}>
                  {t.delta >= 0 ? "+" : ""}
                  {t.delta.toFixed(1)}
                </span>
              </div>
            ))}
          </SpecPanel>

          {diff.blind_spots.length > 0 && (
            <SpecPanel title="Blind Spots" className="cs-blind" plus={false}>
              <p className="cs-blind-lead">
                Sleeves the blind build wants real weight in, where your book
                holds nothing at all:
              </p>
              <ul className="bullets risk">
                {diff.blind_spots.map((b) => (
                  <li key={b.theme}>
                    <b>{b.theme}</b> — {b.target_pct.toFixed(0)}% target, 0% held.
                  </li>
                ))}
              </ul>
            </SpecPanel>
          )}

          {/* the picks */}
          <SpecPanel
            title="The Blind Book"
            aux={`${d.picks.length} positions`}
            className="cs-picks"
          >
            <div className="csp-row csp-head">
              <span>Symbol</span>
              <span>Weight</span>
              <span>Theme</span>
              <span>Why</span>
              <span>Status</span>
            </div>
            {d.picks.map((p) => (
              <div key={p.symbol} className={`csp-row ${held.has(p.symbol) ? "kept" : "fresh"}`}>
                <span className="csp-sym">{p.symbol}</span>
                <span className="csp-pct">{p.pct.toFixed(1)}%</span>
                <span className="csp-theme">{p.theme}</span>
                <span className="csp-why">{p.why}</span>
                <span className="csp-tag">{held.has(p.symbol) ? "held" : "new"}</span>
              </div>
            ))}
          </SpecPanel>

          {d.avoided && d.avoided.length > 0 && (
            <SpecPanel title="Deliberately Left Out" className="cs-avoid" plus={false}>
              <p className="cs-blind-lead">
                What it chose NOT to own. A blind build that skipped these on
                purpose is making a judgement, not diversifying by reflex.
              </p>
              <ul className="bullets">
                {d.avoided.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </SpecPanel>
          )}
        </>
      )}

      <TelemetryStrip
        left={[
          ["Holdings", "HIDDEN"],
          ["Universe", "MARKET"],
          ["Diff", "IN CODE"],
        ]}
        right={[
          ["Model", "BEST"],
          ["Cache", "24H"],
          ["Bias", "TESTED"],
        ]}
        line1="A recommendation you were shown is not a recommendation."
        line2="Build it blind, then compare."
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
