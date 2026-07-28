/* The PROJECT / SYSTEM / VERSION masthead with a registration mark and a
   coordinate readout — the sheet header from the concept posters. */
export function SpecHeader({
  project = "WATCHDOG",
  system = "PORTFOLIO SCANNER",
  version = "2.0",
  coords = ["N 39.0473°", "W 95.6752°"],
}: {
  project?: string;
  system?: string;
  version?: string;
  coords?: [string, string] | string[];
}) {
  return (
    <div className="spec-header">
      <div className="sh-mark">
        <Crosshair />
      </div>
      <div className="sh-fields">
        <div>
          <span className="k">Project:</span>
          <span className="v hot">{project}</span>
        </div>
        <div>
          <span className="k">System:</span>
          <span className="v">{system}</span>
        </div>
        <div>
          <span className="k">Version:</span>
          <span className="v">{version}</span>
        </div>
      </div>
      <div className="sh-coord">
        <Crosshair small />
        <div className="reg-coord">
          {coords.map((c) => (
            <div key={c}>{c}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Crosshair({ small = false }: { small?: boolean }) {
  const s = small ? 18 : 26;
  return (
    <svg
      width={s}
      height={s}
      viewBox="0 0 26 26"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      aria-hidden
    >
      <circle cx="13" cy="13" r="5.2" />
      <circle cx="13" cy="13" r="1.6" fill="currentColor" stroke="none" />
      <path d="M13 0v5M13 21v5M0 13h5M21 13h5" />
    </svg>
  );
}
