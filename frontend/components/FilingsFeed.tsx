"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "../lib/api";

/* Material events, filed — the catalyst feed that covers the whole book.
 *
 * The trial map only speaks for the three pharma names. This is the general
 * answer: an 8-K is a company formally telling the market that something
 * material happened, every US issuer files them, and the item codes make the
 * event type machine-readable — so a merger and an annual-meeting result do
 * not arrive looking the same.
 *
 * Routine filings are hidden behind a toggle rather than deleted. They are the
 * proof that the feed is running on a quiet week, which is worth something,
 * but they are not what you came to read.
 */

interface Filing {
  symbol: string;
  company: string;
  form: string;
  date: string;
  items: string[];
  labels: string[];
  severity: "high" | "medium" | "routine";
  accession: string;
  url: string | null;
}

interface Feed {
  ts: number;
  days: number;
  filings: Filing[];
  no_cik: string[];
}

export function FilingsFeed() {
  const [f, setF] = useState<Feed | null>(null);
  const [showRoutine, setShowRoutine] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/filings`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && Array.isArray(d.filings) && setF(d))
      .catch(() => {});
  }, []);

  if (!f || !f.filings.length) return null;

  const routine = f.filings.filter((x) => x.severity === "routine");
  const shown = showRoutine ? f.filings : f.filings.filter((x) => x.severity !== "routine");
  const highs = f.filings.filter((x) => x.severity === "high").length;

  return (
    <>
      <div className="mfx-label">
        Material events · filed with the SEC · last {f.days} days
      </div>
      <div className="card fil">
        <p className="fil-lead">
          Every name you own, straight from EDGAR. An 8-K is the company itself
          saying something material happened — {highs} of these are the kind
          that change a case rather than tick a box. Filed alongside the press
          release, so this is complete and primary, not early.
        </p>

        <div className="fil-list">
          {shown.map((x) => (
            <a
              key={x.accession}
              className={`fil-row sev-${x.severity}`}
              href={x.url || "#"}
              target="_blank"
              rel="noreferrer"
            >
              <span className="fil-date">{x.date.slice(5)}</span>
              <span className="fil-sym">{x.symbol}</span>
              <span className="fil-form">{x.form}</span>
              <span className="fil-what">{x.labels.join(" · ")}</span>
              <span className="fil-go">Filing →</span>
            </a>
          ))}
        </div>

        {routine.length > 0 && (
          <button className="fil-toggle" onClick={() => setShowRoutine((s) => !s)}>
            {showRoutine ? "Hide" : "Show"} {routine.length} routine filing
            {routine.length === 1 ? "" : "s"}
          </button>
        )}

        {f.no_cik.length > 0 && (
          <p className="fil-note">
            No SEC filer found for {f.no_cik.join(", ")} — foreign issuers file
            different forms and are not covered here.
          </p>
        )}
      </div>
    </>
  );
}
