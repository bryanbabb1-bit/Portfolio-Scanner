"use client";
import { Robustness, RobustnessCell } from "../lib/api";

/* The rule x condition grid. Colour encodes SIGN and strength; a hatched cell
   means the sample is too thin to trust, which is different from a bad result
   and must never look the same as one. */

export function RobustnessMatrix({ r }: { r: Robustness }) {
  if (!r.rules.length) {
    return <div className="spec-empty">{r.note ?? "No signals to grade."}</div>;
  }

  return (
    <div className="rbm">
      <div className="rbm-scroll">
        <table className="rbm-table">
          <thead>
            <tr>
              <th className="rbm-rule-h">Rule</th>
              <th className="rbm-verdict-h">Verdict</th>
              {r.horizons.map((h) => (
                <th key={h} className="rbm-col">
                  {h}
                </th>
              ))}
              {r.regimes.map((g, i) => (
                <th key={g} className={`rbm-col ${i === 0 ? "rbm-divide" : ""}`}>
                  {g}
                  <i>{r.regime_signal_counts[g] ?? 0}</i>
                </th>
              ))}
            </tr>
            <tr className="rbm-grouprow">
              <th />
              <th />
              <th colSpan={r.horizons.length} className="rbm-group">
                measured later
              </th>
              <th colSpan={r.regimes.length} className="rbm-group rbm-divide">
                sample split by market
              </th>
            </tr>
          </thead>
          <tbody>
            {r.rules.map((row) => (
              <tr key={row.rule}>
                <th className="rbm-rule">
                  {row.rule}
                  <i>{row.signals} sig</i>
                </th>
                <td>
                  <span className={`rbm-verdict ${row.verdict.toLowerCase()}`}>
                    {row.verdict}
                  </span>
                </td>
                {r.horizons.map((h) => (
                  <Cell key={h} c={row.cells[h]} />
                ))}
                {r.regimes.map((g, i) => (
                  <Cell key={g} c={row.cells[g]} divide={i === 0} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="rbm-reasons">
        {r.rules.map((row) => (
          <li key={row.rule}>
            <span className={`rbm-dot ${row.verdict.toLowerCase()}`} />
            <b>{row.rule}</b> {row.reason}
          </li>
        ))}
      </ul>

      <p className="rbm-def">
        {r.definition} Hatched cells have fewer than {r.min_cell} signals — too
        thin to judge, which is not the same as a bad result.
      </p>
    </div>
  );
}

function Cell({ c, divide }: { c?: RobustnessCell; divide?: boolean }) {
  if (!c || c.n === 0) {
    return (
      <td className={`rbm-cell empty ${divide ? "rbm-divide" : ""}`}>
        <span className="rbm-none">never fired</span>
      </td>
    );
  }
  const v = c.avg ?? 0;
  // Bucket rather than a continuous ramp: precise shading implies a precision
  // these sample sizes do not have.
  const mag = Math.min(3, Math.ceil(Math.abs(v) / 4));
  const tone = v > 0 ? "pos" : "neg";
  return (
    <td
      className={`rbm-cell ${tone} m${mag} ${c.thin ? "thin" : ""} ${
        divide ? "rbm-divide" : ""
      }`}
      title={`${c.n} signals · ${c.win_rate}% win rate`}
    >
      <span className="rbm-val">
        {v >= 0 ? "+" : ""}
        {v.toFixed(1)}%
      </span>
      <span className="rbm-n">{c.n}</span>
    </td>
  );
}
