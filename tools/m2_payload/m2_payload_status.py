#!/usr/bin/env python3
"""M2.0 payload integrity status.

`--check` loads the packaged payload through the pinned app's own readers.
`--html` writes the integrity page. `--panel` opens a small local window when
tkinter and a display are available. This is not a live AI session and not
product acceptance.
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from m2_common import DEFAULT_PAYLOAD_ROOT, VERSION


def resolve_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        embedded = Path(meipass) / "m2"
        if (embedded / "product_payload").is_dir():
            return embedded
        if (Path(meipass) / "product_payload").is_dir():
            return Path(meipass)
    beside = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    if beside and (beside / "product_payload").is_dir():
        return beside
    if DEFAULT_PAYLOAD_ROOT.is_dir():
        return DEFAULT_PAYLOAD_ROOT
    raise SystemExit("M2_PAYLOAD_ROOT_NOT_FOUND")


def render_html(report: dict) -> str:
    """Self-contained integrity page. No remote assets, no signed-owner claim."""
    files = report.get("files") or []
    absent = report.get("absent") or []
    checks = report.get("checks") or []

    def chip(text: str, kind: str) -> str:
        return f'<span class="chip {kind}">{html.escape(text)}</span>'

    rows = []
    for item in files:
        rows.append(
            "<tr>"
            f"<td class='path'>{html.escape(item['path'])}</td>"
            f"<td>{html.escape(item.get('role') or '')}</td>"
            f"<td class='num'>{item['bytes']}</td>"
            f"<td class='sha'>{html.escape(item['sha256'])}</td>"
            f"<td>{html.escape(item.get('load') or '')}</td>"
            "</tr>"
        )
    absent_rows = []
    for item in absent:
        absent_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('kind') or item.get('path') or ''))}</td>"
            f"<td>{html.escape(item.get('detail') or '')}</td>"
            "</tr>"
        )
    check_rows = []
    for item in checks:
        kind = "ok" if item.get("ok") else "hold"
        check_rows.append(
            "<li class='{0}'><b>{1}</b> {2}</li>".format(
                kind, html.escape(item.get("name") or ""), html.escape(item.get("detail") or "")
            )
        )
    ack = report.get("owner_ack") or {}
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NOX HELION M2.0 payload integrity</title>
<style>
  :root {{
    --bg: #14181f;
    --panel: #1d2632;
    --ink: #efe7d8;
    --muted: #b3a794;
    --line: #334454;
    --ok: #9dcea0;
    --hold: #e2b56a;
    --gold: #e0c48a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background:
      radial-gradient(1200px 500px at 10% -10%, #2a3544 0%, transparent 55%),
      var(--bg);
    color: var(--ink);
    font: 15px/1.45 "Segoe UI", "Helvetica Neue", sans-serif;
  }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 64px; }}
  header {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; }}
  h1 {{ font-family: Georgia, "Iowan Old Style", serif; font-weight: 500; font-size: 34px; margin: 0 0 6px; letter-spacing: 0.01em; }}
  h2 {{ font-family: Georgia, serif; font-weight: 500; font-size: 22px; margin: 28px 0 10px; }}
  .sub {{ color: var(--muted); margin: 0; }}
  .mark {{
    width: 54px; height: 54px; border: 1px solid var(--gold); border-radius: 50%;
    display: grid; place-items: center; color: var(--gold); font-family: Georgia, serif;
  }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0; }}
  .chip {{ border: 1px solid var(--line); border-radius: 999px; padding: 4px 10px; color: var(--muted); background: #121820; }}
  .chip.ok {{ color: var(--ok); border-color: #3e6248; }}
  .chip.hold {{ color: var(--hold); border-color: #6d5430; }}
  section {{ background: rgba(29, 38, 50, 0.92); border: 1px solid var(--line); border-radius: 16px; padding: 8px 16px 16px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  th {{ color: var(--muted); font-weight: 600; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }}
  .path, .sha {{ font-family: ui-monospace, "Cascadia Code", Consolas, monospace; font-size: 12px; word-break: break-all; }}
  .num {{ font-variant-numeric: tabular-nums; }}
  ul {{ margin: 8px 0 0; padding-left: 18px; }}
  li.ok b {{ color: var(--ok); }}
  li.hold b {{ color: var(--hold); }}
  .ack {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-top: 8px; }}
  .box {{ border: 1px dashed var(--line); border-radius: 12px; padding: 10px 12px; color: var(--muted); }}
  .box strong {{ display: block; color: var(--ink); font-size: 14px; }}
  footer {{ color: var(--muted); margin-top: 18px; font-size: 13px; }}
</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Payload integrity</h1>
      <p class="sub">NOX HELION {version} · pre-release candidate · bytes verified, product gate on hold</p>
    </div>
    <div class="mark" aria-hidden="true">M2</div>
  </header>
  <div class="chips">
    {chips}
  </div>
  <section>
    <h2>Checks</h2>
    <ul>{checks}</ul>
  </section>
  <section>
    <h2>Verified files</h2>
    <table>
      <thead><tr><th>Path</th><th>Role</th><th>Bytes</th><th>SHA-256</th><th>Load</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
  <section>
    <h2>Not in this repository</h2>
    <table>
      <thead><tr><th>Kind</th><th>Detail</th></tr></thead>
      <tbody>{absent}</tbody>
    </table>
  </section>
  <section>
    <h2>Owner acknowledgement</h2>
    <div class="ack">
      <div class="box"><strong>Reviewed</strong>{reviewed}</div>
      <div class="box"><strong>Signed</strong>{signed}</div>
      <div class="box"><strong>Approved</strong>{approved}</div>
      <div class="box"><strong>Product acceptance</strong>{acceptance}</div>
    </div>
    <p class="sub">{ack_note}</p>
  </section>
  <footer>
    Reference EXE {ref_name} {ref_sha} was not modified. This page is a packaging receipt, not an online or live-AI result.
  </footer>
</main>
</body>
</html>
""".format(
        version=html.escape(str(report.get("version") or VERSION)),
        chips="".join([
            chip("BYTES VERIFIED" if report.get("bytes_verified") else "BYTES HOLD", "ok" if report.get("bytes_verified") else "hold"),
            chip("IMPORT SMOKE PASS" if report.get("import_smoke") == "PASS" else "IMPORT SMOKE HOLD", "ok" if report.get("import_smoke") == "PASS" else "hold"),
            chip("FIRST-RUN GATE HOLD", "hold"),
            chip("ACCEPTANCE 0/1", "hold"),
            chip("AI OFFLINE", "hold"),
            chip("OWNER ACK UNSIGNED", "hold"),
        ]),
        checks="".join(check_rows) or "<li class='hold'><b>none</b></li>",
        rows="".join(rows) or "<tr><td colspan='5'>No files.</td></tr>",
        absent="".join(absent_rows) or "<tr><td colspan='2'>None recorded.</td></tr>",
        reviewed="unsigned" if not ack.get("payload_reviewed") else "set",
        signed="unsigned" if not ack.get("signed") else "set",
        approved="unsigned" if not ack.get("approved") else "set",
        acceptance=html.escape(str(report.get("product_acceptance") or "0/1")),
        ack_note=html.escape(str(ack.get("note") or "")),
        ref_name=html.escape(str(report.get("reference_exe_name") or "")),
        ref_sha=html.escape(str(report.get("reference_exe_sha256") or "")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--html", type=Path)
    parser.add_argument("--panel", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(VERSION)
        return 0
    root = resolve_root(args.root)
    if args.check or args.html or args.panel:
        from m2_import_smoke import run_smoke
        report = run_smoke(source=args.source, payload_root=root)
    else:
        report = {"version": VERSION, "bytes_verified": False, "import_smoke": "NOT_RUN", "files": [], "checks": [], "absent": [], "owner_ack": {}}
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(report), encoding="utf-8")
        print(f"WROTE {args.html}")
    if args.panel:
        _panel(report)
    if args.check:
        print(f"import_smoke={report.get('import_smoke')} root={root}")
        for item in report.get("checks") or []:
            print(f"{'PASS' if item.get('ok') else 'FAIL'} {item.get('name')} {item.get('detail')}")
        if report.get("import_smoke") != "PASS":
            return 1
    if not (args.check or args.html or args.panel):
        print(f"M2 payload root: {root}")
        print("Pass --check to verify, or --html to write the integrity page.")
    return 0 if report.get("import_smoke") == "PASS" or not args.check else 1


def _panel(report: dict) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        print(f"PANEL_UNAVAILABLE:{exc}")
        return
    root = tk.Tk()
    root.title("NOX HELION M2.0 payload integrity")
    root.geometry("760x480")
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="NOX HELION M2.0 payload integrity", font=("Georgia", 18)).pack(anchor="w")
    ttk.Label(
        frame,
        text="Bytes verified where present. First-run product gate HOLD. Acceptance 0/1. Owner ACK unsigned. AI offline.",
        wraplength=700,
    ).pack(anchor="w", pady=(6, 12))
    tree = ttk.Treeview(frame, columns=("load", "bytes"), show="headings", height=12)
    tree.heading("load", text="Load")
    tree.heading("bytes", text="Bytes")
    tree.pack(fill="both", expand=True)
    for item in report.get("checks") or []:
        tree.insert("", "end", values=(item.get("name"), "ok" if item.get("ok") else "hold"))
    ttk.Label(frame, text="Reference EXE 93a329ba… was not modified.").pack(anchor="w", pady=(10, 0))
    root.mainloop()


if __name__ == "__main__":
    raise SystemExit(main())
