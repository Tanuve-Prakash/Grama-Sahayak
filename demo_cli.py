#!/usr/bin/env python3
"""Terminal chat with the full agent pipeline: no browser, microphone or network needed.
Handy as the 'backup recording' for the demo (slide 5) and for debugging.
   python scripts/demo_cli.py [--lang kn|en] [--trace]      (type  /photo path.jpg  to send a document)"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.i18n import t                       # noqa: E402
from app.orchestrator import Orchestrator    # noqa: E402
from app.session import SessionStore         # noqa: E402


def show(r: dict, trace: bool) -> None:
    print("\n" + (r["display"] if r["cards"] else r["text"]))
    for c in r["cards"]:
        if c["verdict"] == "NEED_INFO":
            continue
        print(f"\n  ┌ {c['name']}  [{c['verdict_label'] or 'info'}]")
        for x in c["reasons"]:
            print("  │", {"pass": "✔", "fail": "✘", "unknown": "?"}[x["status"]], x["text"])
        if c["benefit"]:
            print("  │ ₹", c["benefit"])
        for d in c["documents"]:
            print("  │ ☐", d["name"])
        print("  └ sources:", ", ".join(s["chunk_id"] for s in c["sources"]))
    if r["helplines"] and r["abstained"]:
        print("  ☎ ", ", ".join(f"{h['number']} ({h['name']})" for h in r["helplines"]))
    if r["confirm"]:
        print("  (confirm with yes / no)")
    if trace:
        print("\n  trace:")
        for s in r["trace"]:
            print(f"   {'🛡' if s['kind']=='safety' else '↩' if s['kind']=='loop' else '·'} {s['agent']:22s} {s['summary']}")


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--lang", default="en"); ap.add_argument("--trace", action="store_true")
    a = ap.parse_args()
    o, s = Orchestrator(), SessionStore().create(a.lang)
    print(t("greeting", a.lang)); print("(Ctrl-D to quit; /photo <file> to send a document photo)")
    while True:
        try:
            line = input("\n> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if line.startswith("/photo "):
            p = Path(line[7:].strip()).expanduser()
            r = o.handle_image(s, p.read_bytes(), "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png", a.lang)
        else:
            r = o.handle_text(s, line, a.lang)
        show(r, a.trace)


if __name__ == "__main__":
    main()
