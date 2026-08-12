export const money = (n?: number | null, dp = 2) =>
  n == null ? "—" : `$${n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;

export const pct = (n?: number | null, dp = 2) =>
  n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(dp)}%`;

export const num = (n?: number | null, dp = 2) =>
  n == null ? "—" : n.toFixed(dp);

export const compact = (n?: number | null) => {
  if (n == null) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return `${n}`;
};

export const signClass = (n?: number | null) =>
  n == null ? "mut" : n > 0 ? "pos" : n < 0 ? "neg" : "mut";


/** How long ago something happened, from a unix seconds timestamp.
 *
 * A ruling with no date reads as current no matter how old it is, which is
 * exactly how you end up acting on a week-old argument. Every surface that
 * shows a debate shows its age. */
export function ageFrom(ts?: number | null): string {
  if (!ts) return "";
  const mins = Math.floor((Date.now() / 1000 - ts) / 60);
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "yesterday";
  return `${days}d ago`;
}

/** True once a ruling is old enough that the tape has probably moved on. */
export function isStale(ts?: number | null, days = 7): boolean {
  if (!ts) return false;
  return Date.now() / 1000 - ts > days * 86400;
}
