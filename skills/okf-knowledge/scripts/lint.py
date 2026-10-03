# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Check an OKF v0.2 bundle against the spec and the team's conventions.

    uv run lint.py <bundle> [--base <git-ref>] [--format text|github]

Rules OKF006 and OKF011 compare against --base and are skipped without it.
In CI, pass --conventions-ref (the base branch) so that a pull request cannot
loosen its own rules, and --verify-comments/--writers/--pr-authors so that
OKF006 checks verifications against the pull request's `/okf verify`
comments instead of git author names.

Exit status: 1 when any error is reported, 2 on a git failure, 0 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import _okf


@dataclass
class Finding:
    rule: str
    level: str  # "error" | "warning"
    path: Path
    message: str


# ---- per-file rules ------------------------------------------------------------

def check_concept(c: _okf.Concept, bundle: Path, conv: _okf.Conventions) -> list[Finding]:
    out: list[Finding] = []

    def add(rule: str, level: str, msg: str) -> None:
        out.append(Finding(rule, level, c.path, msg))

    if c.error:
        add("OKF001", "error", c.error)
        return out
    if not c.type:
        add("OKF001", "error", "frontmatter has no non-empty `type` (§11)")
        return out
    fm = c.frontmatter

    for name, value in _okf.timestamp_fields(fm):
        if _okf.parse_ts(value) is None:
            add("OKF002", "error", f"{name} `{value}` is not an ISO 8601 datetime with an offset (§5)")

    for name, value in _okf.path_fields(fm):
        if not isinstance(value, str) or "://" in value:
            continue
        if name == "sources[].resource" and any(ch.isspace() for ch in value):
            continue  # a scope descriptor, not a path (§5.1)
        if not value.startswith("/"):
            add("OKF003", "error", f"{name} `{value}` must be a URL or a bundle path starting with `/`")
        elif not (bundle / value.lstrip("/").split("#")[0]).exists():
            add("OKF004", "warning", f"{name} `{value}` does not exist in the bundle")

    for name, value in _okf.actor_fields(fm):
        if conv.actor_kind(str(value)) is None:
            level = "warning" if name == "sources[].author" else "error"
            add("OKF005", level, f"{name} `{value}` matches no actor pattern in the conventions (§7)")

    if _okf.changed_since_verified(fm):
        add("OKF007", "warning", "generated.at is newer than the latest verified[].at; the change is unverified")

    rule = conv.type_rule(c.type)
    if rule and rule["require_human_verified"]:
        last_human = _okf.latest_verified_at(fm, human_only=True)
        generated = fm.get("generated")
        gen_at = _okf.parse_ts(generated.get("at")) if isinstance(generated, dict) else None
        if last_human is None or (gen_at is not None and gen_at > last_human):
            add("OKF008", "error", f"type `{c.type}` requires a human verification of the current content")

    if rule is None and c.type != _okf.CONVENTIONS_TYPE:
        add("OKF009", "error" if conv.data["unknown_type"] == "error" else "warning",
            f"type `{c.type}` is not in the conventions' vocabulary")
    return out


def check_indexes(bundle: Path) -> list[Finding]:
    out = []
    for path in sorted(p for p in bundle.rglob("index.md") if not _okf.is_hidden(p, bundle)):
        try:
            fm, _, err = _okf.parse_document(_okf.read_text(path))
        except UnicodeDecodeError:
            fm, err = None, "not valid UTF-8"
        if err == "no frontmatter block":
            continue
        allowed = {"okf_version"} if path.parent == bundle else set()
        if fm is None or set(fm) - allowed:
            out.append(Finding("OKF010", "error", path,
                               "index.md carries no frontmatter, except `okf_version` at the bundle root (§8)"))
    return out


# ---- rules against --base ---------------------------------------------------------

class GitError(Exception):
    pass


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false", *args],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def show(root: Path, rev: str, rel: str) -> str | None:
    try:
        return git(root, "show", f"{rev}:{rel}")
    except GitError:
        return None


def name_status(output: str) -> list[tuple[str, str | None, str | None]]:
    """(status, old path, new path) from `--name-status -z` output."""
    parts = output.split("\0")
    out, i = [], 0
    while i < len(parts) and parts[i]:
        status = parts[i]
        if status[0] in "RC":
            out.append((status[0], parts[i + 1], parts[i + 2]))
            i += 3
        else:
            path = parts[i + 1]
            out.append((status[0], None if status[0] == "A" else path, None if status[0] == "D" else path))
            i += 2
    return out


def version_at(root: Path, rev: str, rel: str | None) -> tuple[dict | None, str, bool]:
    """(frontmatter, body, known). known is False when the file exists but does not parse."""
    if rel is None:
        return {}, "", True
    text = show(root, rev, rel)
    if text is None:
        return {}, "", True
    fm, body, _ = _okf.parse_document(text.removeprefix("\ufeff"))
    return fm, body, fm is not None


def human_verifications(fm: dict | None) -> set[tuple[str, str]]:
    return {(str(e.get("by")), str(e.get("at"))) for e in _okf.normalize_verified(fm or {})
            if str(e.get("by") or "").startswith("human:")}


def _content(fm: dict) -> dict:
    """Frontmatter without the keys a verification or regeneration touches."""
    return {k: v for k, v in fm.items() if k not in ("verified", "generated")}


def _generated_at(fm: dict):
    generated = fm.get("generated")
    return generated.get("at") if isinstance(generated, dict) else None


@dataclass
class Attestation:
    """A `/okf verify` comment by someone allowed to verify."""
    by: str
    at: str
    paths: frozenset[str]


def attestations_from_comments(comments: list[dict], writers: set[str], excluded: set[str]) -> list[Attestation]:
    """GitHub issue comments → attestations. Comments by non-writers or excluded logins do not count."""
    out = []
    for c in comments:
        parsed = _okf.parse_verify_comment(str(c.get("body") or ""))
        login = str((c.get("user") or {}).get("login") or "")
        if parsed is None or login not in writers or login in excluded:
            continue
        out.append(Attestation(f"human:{login}", str(c.get("created_at")), frozenset(parsed[1])))
    return out


def check_history(bundle: Path, base: str, conv: _okf.Conventions,
                  attestations: list[Attestation] | None) -> list[Finding]:
    """OKF006 and OKF011 over the net change merge-base(base, HEAD)..HEAD.

    With attestations (CI), every added human: verification must match a
    `/okf verify` comment: same person, same time, and the file among its
    paths. Without them (a local run), OKF006 falls back to checking the git
    author of each commit, which catches mistakes but can be forged.
    """
    root = Path(git(bundle, "rev-parse", "--show-toplevel").strip())
    rel_bundle = bundle.resolve().relative_to(root.resolve()).as_posix()
    merge_base = git(root, "merge-base", base, "HEAD").strip()
    out: list[Finding] = []
    added_by_path: dict[str, set[tuple[str, str]]] = {}

    changes = name_status(git(root, "diff", "-z", "--name-status", "-M", merge_base, "HEAD", "--", rel_bundle))
    for status, old_rel, new_rel in changes:
        if new_rel is None or not new_rel.endswith(".md") or Path(new_rel).name in _okf.RESERVED:
            continue
        old, old_body, old_known = version_at(root, merge_base, old_rel)
        new, new_body, new_known = version_at(root, "HEAD", new_rel)
        if not new_known:
            continue  # OKF001 reports it
        added = human_verifications(new) - human_verifications(old)
        if added and not old_known:
            out.append(Finding("OKF006", "warning", root / new_rel,
                               "the base version does not parse, so added verifications cannot be told apart"))
        elif added:
            added_by_path[new_rel] = added

        if status in "MR" and old_known and Path(new_rel).name != _okf.CONVENTIONS_FILE:
            content_changed = _content(old) != _content(new) or old_body != new_body
            if content_changed and _generated_at(old) == _generated_at(new):
                out.append(Finding("OKF011", "warning", root / new_rel,
                                   "content changed but generated.at did not; update generated.by/at"))

    if attestations is not None:
        for rel, added in sorted(added_by_path.items()):
            for by, at in sorted(added):
                if not any(a.by == by and a.at == at and rel in a.paths for a in attestations):
                    out.append(Finding("OKF006", "error", root / rel,
                                       f"verification `{by}` at {at} matches no `/okf verify` comment "
                                       f"by a writer that lists {rel}"))
    elif added_by_path:
        out += _check_authors(root, base, rel_bundle, conv, added_by_path)
    return out


def _check_authors(root: Path, base: str, rel_bundle: str, conv: _okf.Conventions,
                   added_by_path: dict[str, set[tuple[str, str]]]) -> list[Finding]:
    bot = conv.data["verify"]["bot_git_author"]
    out = []
    for commit in git(root, "rev-list", "--reverse", f"{base}..HEAD").split():
        author = git(root, "show", "-s", "--format=%an", commit).strip()
        if author == bot:
            continue
        parents = git(root, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        diff = git(root, "diff-tree", "-z", "-r", "-M", "--root", "--name-status", "--no-commit-id",
                   *( [parents[0], commit] if parents else [commit] ), "--", rel_bundle)
        for _, old_rel, new_rel in name_status(diff):
            if new_rel not in added_by_path:
                continue
            old, _, _ = version_at(root, parents[0], old_rel) if parents else ({}, "", True)
            new, _, _ = version_at(root, commit, new_rel)
            for by, at in sorted((human_verifications(new) - human_verifications(old)) & added_by_path[new_rel]):
                out.append(Finding("OKF006", "error", root / new_rel,
                                   f"commit {commit[:12]} by `{author}` adds verification `{by}` at {at}; "
                                   f"only `{bot}` may add human: verifications"))
    return out


# ---- entry point ----------------------------------------------------------------------

def lint(bundle: Path, base: str | None = None, conventions_text: str | None = None,
         attestations: list[Attestation] | None = None) -> list[Finding]:
    conv = _okf.load_conventions(bundle, conventions_text)
    findings = [Finding("CONV", "warning", bundle / _okf.CONVENTIONS_FILE, w) for w in conv.warnings]
    for c in _okf.load_concepts(bundle):
        findings += check_concept(c, bundle, conv)
    findings += check_indexes(bundle)
    if base:
        findings += check_history(bundle, base, conv, attestations)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--base", help="git ref to compare against (enables OKF006 and OKF011)")
    ap.add_argument("--conventions-ref", help="read CONVENTIONS.md from this git ref instead of the working tree")
    ap.add_argument("--verify-comments", type=Path,
                    help="JSON array of the pull request's issue comments; OKF006 then checks against them")
    ap.add_argument("--writers", default="", help="comma-separated logins with write access")
    ap.add_argument("--pr-authors", default="", help="comma-separated logins of the pull request's authors")
    ap.add_argument("--format", choices=("text", "github"), default="text")
    args = ap.parse_args()

    try:
        conventions_text = None
        if args.conventions_ref:
            root = Path(git(args.bundle, "rev-parse", "--show-toplevel").strip())
            rel = (args.bundle.resolve() / _okf.CONVENTIONS_FILE).relative_to(root.resolve()).as_posix()
            conventions_text = show(root, args.conventions_ref, rel) or ""
        attestations = None
        if args.verify_comments:
            conv = _okf.load_conventions(args.bundle, conventions_text)
            excluded = set() if conv.data["verify"]["allow_self_verify"] else _logins(args.pr_authors)
            comments = json.loads(args.verify_comments.read_text(encoding="utf-8"))
            attestations = attestations_from_comments(comments, _logins(args.writers), excluded)
        findings = lint(args.bundle, args.base, conventions_text, attestations)
    except GitError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    for f in findings:
        rel = os.path.relpath(f.path)
        if args.format == "github":
            print(f"::{f.level} file={rel},line=1,title={f.rule}::{f.message}")
        else:
            print(f"{f.level.upper():<7} {f.rule} {rel}: {f.message}")
    errors = sum(f.level == "error" for f in findings)
    print(f"{errors} error(s), {len(findings) - errors} warning(s)", file=sys.stderr)
    return 1 if errors else 0


def _logins(csv: str) -> set[str]:
    return {x.strip() for x in csv.split(",") if x.strip()}


if __name__ == "__main__":
    sys.exit(main())
