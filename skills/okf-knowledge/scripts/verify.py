# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Append a human verification to concepts of an OKF v0.2 bundle (§5.2).

    uv run verify.py <bundle> <path>... --by human:<id> --at <iso8601> [options]
    uv run verify.py <bundle> --comment <file> --head-sha <sha> --by ... --at ... [options]

Meant to be run by the okf-verify workflow, never by an agent on its own
behalf. The frontmatter is edited as text: only the lines of `verified` change,
so every other key keeps its layout, quoting and timestamps byte for byte.
All paths are checked before any file is written; one bad path writes nothing.

Options for the workflow:
  --comment       read `/okf verify [@<sha>] <path>...` from a file instead of
                  taking paths as arguments; the named sha must prefix
                  --head-sha, and conventions with require_sha demand one
  --repo-root     resolve paths (and --changed) against this directory
  --conventions   a CONVENTIONS.md to use instead of the bundle's own (the
                  base branch's copy, so a pull request cannot loosen it)
  --pr-authors    comma-separated logins who opened or committed to the pull
                  request; refused as verifiers when self-verification is off
  --changed       a file listing the pull request's changed paths, one per
                  line; other paths are refused
  --commit        commit the written files as the conventions' bot_git_author

Exit status: 0 written or already verified, 2 invalid input, 3 unsupported
`verified` layout (edit that file by hand).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import _okf

_KEY = re.compile(r"^verified\s*:(.*?)(\r?\n)?$")


class Unsupported(Exception):
    pass


def _continuation_end(lines: list[str], start: int, stop: int) -> int:
    """Index after the lines that belong to the key on lines[start]."""
    k = start + 1
    last = start
    while k < stop:
        line = lines[k]
        if line.strip() == "":
            k += 1
            continue
        if line[0] in " \t" or line.startswith("-"):
            last = k
            k += 1
            continue
        break
    return last + 1


def _entry(by: str, at: str) -> str:
    return f"{{ by: {by}, at: {at} }}"


def add_verification(text: str, by: str, at: str) -> str:
    """Return text with one more `verified` entry. Raises Unsupported."""
    lines = text.splitlines(keepends=True)
    close = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    nl = "\r\n" if lines[0].endswith("\r\n") else "\n"
    key = next((i for i in range(1, close) if _KEY.match(lines[i])), None)

    if key is None:
        new = [f"verified:{nl}", f"  - {_entry(by, at)}{nl}"]
        return "".join(lines[:close] + new + lines[close:])

    rest = _KEY.match(lines[key]).group(1).strip()
    end = _continuation_end(lines, key, close)
    block = lines[key + 1:end]

    if rest.startswith("{"):  # bare flow mapping on the key line
        if not rest.endswith("}") or block:
            raise Unsupported("multi-line flow mapping")
        new = [f"verified:{nl}", f"  - {rest}{nl}", f"  - {_entry(by, at)}{nl}"]
        return "".join(lines[:key] + new + lines[end:])
    if rest.startswith("["):
        raise Unsupported("flow sequence")
    if rest and not rest.startswith("#"):
        raise Unsupported(f"unexpected value `{rest}`")

    items = [ln for ln in block if ln.strip()]
    if not items:
        raise Unsupported("empty verified block")
    first = items[0]
    indent = len(first) - len(first.lstrip(" "))
    if first.lstrip(" ").startswith("-"):  # block sequence: append an item
        new_item = f"{' ' * indent}- {_entry(by, at)}{nl}"
        return "".join(lines[:end] + [new_item] + lines[end:])

    # bare block mapping: turn it into the first item of a sequence
    converted = []
    for i, ln in enumerate(block):
        if not ln.strip():
            converted.append(ln)
        elif i == block.index(first):
            converted.append(f"{' ' * indent}- {ln[indent:]}")
        else:
            converted.append(f"  {ln}")
    new_item = f"{' ' * indent}- {_entry(by, at)}{nl}"
    return "".join(lines[:key + 1] + converted + [new_item] + lines[end:])


def plan(repo_root: Path, bundle: Path, paths: list[str], by: str, at: str, conv: _okf.Conventions,
         pr_authors: set[str] = frozenset(), changed: set[str] | None = None) -> list[tuple[Path, str | None]]:
    """Validate every path; return [(file, new text or None if already verified)]."""
    if not re.match(conv.data["actors"]["human_pattern"], by):
        raise ValueError(f"--by `{by}` is not a human actor")
    if by in {f"human:{a}" for a in pr_authors} and not conv.data["verify"]["allow_self_verify"]:
        raise ValueError(f"{by} opened or committed to the pull request, "
                         "and the conventions disallow self-verification")
    if _okf.parse_ts(at) is None:
        raise ValueError(f"--at `{at}` is not an ISO 8601 datetime with an offset")
    if not paths:
        raise ValueError("no paths to verify")
    root = bundle.resolve()
    repo = repo_root.resolve()
    out = []
    for raw in paths:
        p = Path(raw)
        if ".." in p.parts:
            raise ValueError(f"{raw}: `..` is not allowed")
        full = (repo / p).resolve()
        if not full.is_relative_to(root):
            raise ValueError(f"{raw}: outside the bundle {bundle}")
        if full.suffix != ".md" or full.name in _okf.RESERVED or not full.is_file():
            raise ValueError(f"{raw}: not a concept file")
        if changed is not None and full.relative_to(repo).as_posix() not in changed:
            raise ValueError(f"{raw}: not changed by this pull request")
        try:
            with open(full, encoding="utf-8", newline="") as f:  # keep CRLF as written
                text = f.read()
        except UnicodeDecodeError as e:
            raise ValueError(f"{raw}: not valid UTF-8") from e
        bom = "\ufeff" if text.startswith("\ufeff") else ""
        text = text.removeprefix(bom)
        fm, _, err = _okf.parse_document(text)
        if err or not fm.get("type"):
            raise ValueError(f"{raw}: {err or 'no type'}")
        before = _okf.normalize_verified(fm)
        if any(str(e.get("by")) == by and str(e.get("at")) == at for e in before):
            out.append((full, None))
            continue
        try:
            new = add_verification(text, by, at)
        except Unsupported as e:
            raise Unsupported(f"{raw}: {e}") from e
        after, _, err = _okf.parse_document(new)
        expected = before + [{"by": by, "at": at}]
        if err or _okf.normalize_verified(after) != expected or _without_verified(after) != _without_verified(fm):
            raise Unsupported(f"{raw}: edit did not round-trip")
        out.append((full, bom + new))
    return out


def _without_verified(fm: dict) -> dict:
    return {k: v for k, v in fm.items() if k != "verified"}


def paths_from_comment(body: str, head_sha: str | None, conv: _okf.Conventions) -> list[str]:
    parsed = _okf.parse_verify_comment(body)
    if parsed is None:
        raise ValueError("the comment is not `/okf verify [@<sha>] <path>...`")
    sha, paths = parsed
    if sha is None and conv.data["verify"]["require_sha"]:
        raise ValueError("name the commit you checked: `/okf verify @<sha> <path>...`")
    if sha is not None and not (head_sha or "").startswith(sha):
        raise ValueError(f"@{sha} is not the pull request's head commit {(head_sha or '?')[:12]}; "
                         "check the latest changes and comment again")
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--by", required=True)
    ap.add_argument("--at", required=True)
    ap.add_argument("--comment", type=Path)
    ap.add_argument("--head-sha")
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--conventions", type=Path)
    ap.add_argument("--pr-authors", default="")
    ap.add_argument("--changed", type=Path)
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    try:
        conv_text = _okf.read_text(args.conventions) if args.conventions else None
        conv = _okf.load_conventions(args.bundle, conv_text)
        paths = list(args.paths)
        if args.comment:
            if paths:
                raise ValueError("give paths either as arguments or in --comment, not both")
            paths = paths_from_comment(_okf.read_text(args.comment), args.head_sha, conv)
        changed = None
        if args.changed:
            changed = {ln.strip() for ln in _okf.read_text(args.changed).splitlines() if ln.strip()}
        authors = {x.strip() for x in args.pr_authors.split(",") if x.strip()}
        changes = plan(args.repo_root, args.bundle, paths, args.by, args.at, conv, authors, changed)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Unsupported as e:
        print(f"error: unsupported verified layout: {e}", file=sys.stderr)
        return 3
    for path, new in changes:
        if new is None:
            print(f"already verified: {path}")
        else:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            print(f"verified: {path}")
    written = [str(p) for p, new in changes if new is not None]
    if args.commit and written:
        commit(args.bundle, written, args.by, conv.data["verify"]["bot_git_author"])
    return 0


def commit(bundle: Path, files: list[str], by: str, bot: str) -> None:
    """Commit in the repository that holds the bundle, whatever the working directory."""
    git = ["git", "-C", str(bundle), "-c", f"user.name={bot}",
           "-c", f"user.email={bot}@users.noreply.github.com"]
    subprocess.run([*git, "add", "--", *files], check=True)
    names = ", ".join(Path(f).name for f in files)
    subprocess.run([*git, "commit", "-q", "-m", f"okf: verify {names} by {by}"], check=True)


if __name__ == "__main__":
    sys.exit(main())
