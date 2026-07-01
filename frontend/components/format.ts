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
