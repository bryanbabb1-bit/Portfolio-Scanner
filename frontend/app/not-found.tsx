import Link from "next/link";
import { SpecHeader, SpecPanel } from "../components/blueprint";

/* Next's built-in 404 renders on a dark background and offers no way back,
   which reads like the app broke. This one stays in the blueprint palette and
   points at the pages that still exist. */
export default function NotFound() {
  return (
    <>
      <SpecHeader system="PAGE NOT FOUND" version="2.0" />
      <div className="sheet-rule">404</div>

      <SpecPanel title="No Such Sheet" plus={false} className="nf-panel">
        <h1 className="display-head nf-head">
          That page
          <br />
          <span className="dh-alt">isn&apos;t here.</span>
        </h1>
        <div className="dh-rule" />
        <p className="nf-body">
          Strategy, Transition Plan and Clean Sheet were retired — the brief
          now produces the plan itself, so there is one set of orders instead
          of four that disagreed. Old links land here.
        </p>
        <div className="nf-links">
          <Link href="/" className="btn">
            Dashboard
          </Link>
          <Link href="/risk" className="btn ghost">
            Risk Desk
          </Link>
          <Link href="/debate" className="btn ghost">
            Agent Debate
          </Link>
          <Link href="/settings" className="btn ghost">
            Settings
          </Link>
        </div>
      </SpecPanel>
    </>
  );
}
