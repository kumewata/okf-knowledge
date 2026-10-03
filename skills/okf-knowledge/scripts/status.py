# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""List the concepts of an OKF v0.2 bundle that need attention.

    uv run status.py <bundle> [--now <iso8601>] [--format md|json]

Sections: stale (now >= stale_after), deprecated, unverified, changed since
the last verification (generated.at newer than verified[].at), and
unreadable (no parseable frontmatter or no `type`). A concept can appear in
more than one section. --now defaults to the current time in UTC.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import _okf

SECTIONS = (
    ("stale", "Stale"),
    ("deprecated", "Deprecated"),
    ("unverified", "Unverified"),
    ("changed_since_verified", "Changed since verification"),
    ("unreadable", "Unreadable"),
)


def classify(bundle: Path, now: datetime) -> list[dict]:
    rows = []
    for c in _okf.load_concepts(bundle):
        fm = c.frontmatter
        readable = c.error is None and bool(c.type)
        rows.append({
            "cid": c.cid,
            "title": str(fm.get("title") or c.path.stem),
            "type": c.type,
            "status": str(fm.get("status") or "stable"),  # §5.4: absent ⇒ stable
            "tier": _okf.trust_tier(fm),
            "stale_after": str(fm.get("stale_after") or ""),
            "stale": readable and _okf.is_stale(fm, now),
            "deprecated": readable and fm.get("status") == "deprecated",
            "unverified": readable and _okf.trust_tier(fm) == "unverified",
            "changed_since_verified": readable and _okf.changed_since_verified(fm),
            "unreadable": not readable,
        })
    return rows


def to_markdown(rows: list[dict], now: datetime) -> str:
    lines = [f"OKF bundle status as of {now.isoformat()}", ""]
    for key, heading in SECTIONS:
        hits = [r for r in rows if r[key]]
        lines.append(f"## {heading} ({len(hits)})")
        lines.append("")
        for r in hits:
            detail = r["tier"] + (f", stale_after {r['stale_after']}" if r["stale_after"] else "")
            lines.append(f"- [{r['title']}](/{r['cid']}.md) — {detail}")
        if not hits:
            lines.append("_none_")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--now", help="ISO 8601 datetime with an offset (default: now, UTC)")
    ap.add_argument("--format", choices=("md", "json"), default="md")
    args = ap.parse_args()

    now = _okf.now_utc()
    if args.now:
        now = _okf.parse_ts(args.now)
        if now is None:
            ap.error("--now must be an ISO 8601 datetime with an offset")
    rows = classify(args.bundle, now)
    print(json.dumps(rows, ensure_ascii=False, indent=2) if args.format == "json" else to_markdown(rows, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
