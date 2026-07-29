/* After Hours — paper by day, terminal by night.
 *
 * Three preferences, not two. "auto" is the concept working on its own: the
 * desk is on paper while the market is open and drops to phosphor once it
 * closes. Day and Night pin it, because a theme that changes under you at
 * 4:00pm while you are reading something is a bug, not a feature — the pin is
 * what makes the automatic behaviour safe to ship as the default.
 */

export type ThemePref = "auto" | "day" | "night";
export type Theme = "day" | "night";

export const THEME_KEY = "wd.theme";

/** Market session in ET, DST-correct — the browser's tz database does the work. */
export function marketOpen(now = new Date()): boolean {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "numeric",
    weekday: "short",
    hour12: false,
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  // hour12:false yields "24" for midnight in some engines.
  const mins = (Number(get("hour")) % 24) * 60 + Number(get("minute"));
  const weekday = ["Mon", "Tue", "Wed", "Thu", "Fri"].includes(get("weekday"));
  return weekday && mins >= 9 * 60 + 30 && mins < 16 * 60;
}

/** ?theme=day|night previews a theme for one page load without saving it. */
export function previewTheme(): Theme | null {
  if (typeof window === "undefined") return null;
  const t = new URLSearchParams(window.location.search).get("theme");
  return t === "day" || t === "night" ? t : null;
}

export function resolveTheme(pref: ThemePref, now = new Date()): Theme {
  return previewTheme() ?? (pref === "auto" ? (marketOpen(now) ? "day" : "night") : pref);
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "night") root.setAttribute("data-theme", "night");
  else root.removeAttribute("data-theme");
  // Keep the mobile browser chrome in step, or the notch band stays paper
  // while the page goes black.
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "night" ? "#0B0B09" : "#F2EEE4");
}

/* The same resolution, inlined into <head> so it runs BEFORE first paint.
   Without this the page renders paper and then snaps to black on hydration —
   the one flash that makes a dark theme feel cheap. Kept deliberately terse
   and wrapped in try/catch: it runs before React and must never throw. */
export const THEME_BOOT_SCRIPT = `(function(){try{
var p=localStorage.getItem(${JSON.stringify(THEME_KEY)})||"auto",t=p;
var o=new URLSearchParams(location.search).get("theme");
if(o==="day"||o==="night"){p=t=o;}
else if(p==="auto"){var q={};new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",minute:"numeric",weekday:"short",hour12:false}).formatToParts(new Date()).forEach(function(x){q[x.type]=x.value});
var m=(+q.hour%24)*60+ +q.minute;t=(["Mon","Tue","Wed","Thu","Fri"].indexOf(q.weekday)>=0&&m>=570&&m<960)?"day":"night";}
if(t==="night"){document.documentElement.setAttribute("data-theme","night");
var m=document.querySelector('meta[name="theme-color"]');if(m){m.setAttribute("content","#0B0B09");}}
}catch(e){}})();`;
