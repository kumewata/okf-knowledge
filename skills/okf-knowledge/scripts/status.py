# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3"]
# ///
"""List the concepts of an OKF v0.2 bundle that need attention.

    uv run status.py <bundle> [--now <iso8601>] [--format md|json] [--link-prefix <url>]

Sections: stale (now >= stale_after), deprecated, unverified, changed since
the last verification (generated.at newer than verified[].at), and
unreadable (no parseable frontmatter or no `type`). A concept can appear in
more than one section. The conventions file (`type: OKF Conventions`) is
not listed: it holds rules, not knowledge. --now defaults to the current
time in UTC.

Links in the markdown are the concept path after --link-prefix, which
defaults to `/` (a bundle path, §6.1). For an issue body, pass the bundle's
URL, such as https://github.com/<owner>/<repo>/blob/main/knowledge/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

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
        if c.type == _okf.CONVENTIONS_TYPE:
            continue
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


def to_markdown(rows: list[dict], now: datetime, link_prefix: str = "/") -> str:
    lines = [f"OKF bundle status as of {now.isoformat()}", ""]
    for key, heading in SECTIONS:
        hits = [r for r in rows if r[key]]
        lines.append(f"## {heading} ({len(hits)})")
        lines.append("")
        for r in hits:
            detail = r["tier"] + (f", stale_after {r['stale_after']}" if r["stale_after"] else "")
            lines.append(f"- [{r['title']}]({link_prefix}{quote(r['cid'])}.md) — {detail}")
        if not hits:
            lines.append("_none_")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--now", help="ISO 8601 datetime with an offset (default: now, UTC)")
    ap.add_argument("--format", choices=("md", "json"), default="md")
    ap.add_argument("--link-prefix", default="/", help="prepended to each concept path in markdown links")
    args = ap.parse_args()

    now = _okf.now_utc()
    if args.now:
        now = _okf.parse_ts(args.now)
        if now is None:
            ap.error("--now must be an ISO 8601 datetime with an offset")
    rows = classify(args.bundle, now)
    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(to_markdown(rows, now, args.link_prefix))
    return 0


if __name__ == "__main__":
    sys.exit(main())
