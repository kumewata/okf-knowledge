# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Generate the index.md files of an OKF v0.2 bundle (§8).

    uv run index.py <bundle> [--check]

Each directory that holds concepts gets an index.md listing its concepts
(title and description from frontmatter, by file name) and then its
subdirectories. An index.md in a subdirectory with no concepts left is
removed. A frontmatter block on the bundle-root index.md (where `okf_version`
lives) is kept as written. --check writes nothing and exits 1
when any index.md differs from what would be generated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _okf


def _one_line(value) -> str:
    return " ".join(str(value or "").split())


def _has_concepts(directory: Path) -> bool:
    return bool(_okf.concept_paths(directory))


def _target(name: str) -> str:
    """A CommonMark link destination; names with spaces or parentheses go in <...>."""
    return f"<{name}>" if any(ch in name for ch in " ()<>") else name


def render_indexes(bundle: Path) -> dict[Path, str | None]:
    """{path of each index.md: its full expected text, or None if it should not exist}."""
    out: dict[Path, str | None] = {}
    dirs = [bundle] + sorted(d for d in bundle.rglob("*") if d.is_dir() and not _okf.is_hidden(d, bundle))
    for d in dirs:
        if not _has_concepts(d):
            if d != bundle and (d / "index.md").exists():
                out[d / "index.md"] = None
            continue
        lines = [f"# {bundle.resolve().name if d == bundle else d.name}", ""]
        for path in sorted(p for p in d.glob("*.md") if p.name not in _okf.RESERVED):
            try:
                fm, _, _ = _okf.parse_document(_okf.read_text(path))
            except UnicodeDecodeError:
                fm = None
            fm = fm or {}
            title = _one_line(fm.get("title")) or path.stem
            desc = _one_line(fm.get("description"))
            lines.append(f"* [{title}]({_target(path.name)})" + (f" - {desc}" if desc else ""))
        for sub in sorted(s for s in d.iterdir() if s.is_dir() and not s.name.startswith(".")):
            if _has_concepts(sub):
                lines.append(f"* [{sub.name}]({_target(sub.name + '/index.md')})")
        text = "\n".join(lines) + "\n"

        index = d / "index.md"
        if d == bundle and index.exists():
            existing = _okf.read_text(index)
            fm, _, err = _okf.parse_document(existing)
            if err is None:
                head_end = existing.index("\n---", 3) + len("\n---")
                text = existing[:head_end].rstrip("\n") + "\n\n" + text
        out[index] = text
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--check", action="store_true", help="exit 1 if any index.md is out of date")
    args = ap.parse_args()

    stale = []
    for path, text in render_indexes(args.bundle).items():
        current = _okf.read_text(path) if path.exists() else None
        if current == text:
            continue
        stale.append(path)
        if args.check:
            continue
        if text is None:
            path.unlink()  # a generated index of a directory that no longer holds concepts
        else:
            path.write_text(text, encoding="utf-8")
    for path in stale:
        print(f"{'out of date' if args.check else 'updated'}: {path}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
