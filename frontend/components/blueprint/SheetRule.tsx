/* Dashed sheet rule with a page/section number, like the poster's "04/08". */
export function SheetRule({ mark }: { mark: string }) {
  return <div className="sheet-rule">{mark}</div>;
}
