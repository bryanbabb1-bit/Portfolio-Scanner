import { Signal } from "../lib/api";

export function Signals({ signals, max }: { signals: Signal[]; max?: number }) {
  const list = max ? signals.slice(0, max) : signals;
  return (
    <div className="signals">
      {list.map((s, i) => (
        <span key={i} className={`sig ${s.kind}`} title={s.detail}>
          {s.label}
        </span>
      ))}
    </div>
  );
}
