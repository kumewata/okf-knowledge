"""Shared helpers for the okf-knowledge scripts (OKF v0.2).

Not a standalone script: lint.py, status.py, index.py and verify.py import it
from their own directory, and each of them declares the PyYAML dependency in
its PEP 723 header.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

RESERVED = frozenset({"index.md", "log.md"})
SUPPORTED_OKF_VERSIONS = ("0.2",)
LINT_RULES = tuple(f"OKF{n:03d}" for n in range(1, 13))
CONVENTIONS_FILE = "CONVENTIONS.md"
CONVENTIONS_TYPE = "OKF Conventions"


# ---- YAML --------------------------------------------------------------------

class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps timestamps as the text the author wrote.

    PyYAML implements YAML 1.1 and would turn `2026-06-30T14:00:00Z` into a
    datetime, dropping the distinction between a date-only value and an
    instant with an offset. Same approach as the OKF reference implementation
    (GoogleCloudPlatform/open-knowledge-format,
    src/reference_agent/bundle/document.py, Apache-2.0).
    """


_Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def parse_document(text: str) -> tuple[dict[str, Any] | None, str, str | None]:
    """Split a markdown file into (frontmatter, body, error).

    frontmatter is None when the file has no frontmatter block or it cannot be
    parsed; error says why in the latter case.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text, "no frontmatter block"
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            break
    else:
        return None, text, "unterminated frontmatter block"
    try:
        fm = yaml.load("\n".join(lines[1:i]), Loader=_Loader) or {}
    except yaml.YAMLError as e:
        return None, text, f"invalid YAML in frontmatter: {e}"
    if not isinstance(fm, dict):
        return None, text, "frontmatter is not a mapping"
    return fm, "\n".join(lines[i + 1:]), None


# ---- concepts ----------------------------------------------------------------

@dataclass
class Concept:
    path: Path
    cid: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    error: str | None = None

    @property
    def type(self) -> str:
        return str(self.frontmatter.get("type") or "")


def read_text(path: Path) -> str:
    """UTF-8 text with a leading BOM dropped. Raises UnicodeDecodeError."""
    return path.read_text(encoding="utf-8-sig")


def is_hidden(path: Path, root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def concept_paths(bundle: Path) -> list[Path]:
    """Every non-reserved .md file under the bundle, outside dot-directories (§3.1)."""
    return sorted(p for p in bundle.rglob("*.md") if p.name not in RESERVED and not is_hidden(p, bundle))


def load_concepts(bundle: Path) -> list[Concept]:
    out = []
    for path in concept_paths(bundle):
        cid = path.relative_to(bundle).with_suffix("").as_posix()
        try:
            fm, body, err = parse_document(read_text(path))
        except UnicodeDecodeError:
            fm, body, err = None, "", "not valid UTF-8"
        out.append(Concept(path, cid, fm or {}, body, err))
    return out


# ---- conventions -------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "types": {
        "Runbook": {"stale_after_days": 180, "require_human_verified": False},
        "ADR": {"stale_after_days": 365, "require_human_verified": False},
        "Table": {"stale_after_days": 180, "require_human_verified": False},
        "Metric": {"stale_after_days": 180, "require_human_verified": False},
        "Glossary": {"stale_after_days": 365, "require_human_verified": False},
        "Reference": {"stale_after_days": 90, "require_human_verified": False},
        "Note": {"stale_after_days": 90, "require_human_verified": False},
    },
    "unknown_type": "warn",
    "verify": {"allow_self_verify": True, "require_sha": True, "bot_git_author": "okf-verify[bot]"},
    "lint": {"strict": []},
    "actors": {
        "agent_pattern": r"^claude-code/\S+$",
        "human_pattern": r"^human:[A-Za-z0-9_-]+$",
        "process_pattern": r"^process:[a-z0-9-]+$",
    },
}


@dataclass
class Conventions:
    data: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    @property
    def types(self) -> dict[str, dict[str, Any]]:
        return self.data["types"]

    def type_rule(self, type_name: str) -> dict[str, Any] | None:
        return self.types.get(type_name)

    def actor_kind(self, actor: str) -> str | None:
        """'human', 'agent' or 'process' when the actor matches a pattern."""
        for kind in ("human", "agent", "process"):
            if re.match(self.data["actors"][f"{kind}_pattern"], actor):
                return kind
        return None


def _check_type_entry(name: Any, entry: Any) -> str | None:
    if not isinstance(name, str) or not isinstance(entry, dict):
        return f"types.{name}: must be a mapping"
    days = entry.get("stale_after_days")
    if days is not None and (isinstance(days, bool) or not isinstance(days, int) or days <= 0):
        return f"types.{name}.stale_after_days: must be a positive integer or null"
    req = entry.get("require_human_verified", False)
    if not isinstance(req, bool):
        return f"types.{name}.require_human_verified: must be true or false"
    unknown = set(entry) - {"stale_after_days", "require_human_verified"}
    if unknown:
        return f"types.{name}: unknown key(s) {sorted(unknown)}"
    return None


def load_conventions(bundle: Path, text: str | None = None) -> Conventions:
    """Read okf_conventions from <bundle>/CONVENTIONS.md, filling defaults.

    `text`, when given, is used instead of the file: CI passes the base
    branch's version so that a pull request cannot loosen its own rules.
    A given `types` mapping replaces the default vocabulary; any other key that
    is missing keeps its default. An invalid value falls back to the default
    and is reported in `warnings`.
    """
    data = copy.deepcopy(DEFAULTS)
    warnings: list[str] = []
    if text is None:
        path = bundle / CONVENTIONS_FILE
        if not path.exists():
            return Conventions(data, warnings)
        text = read_text(path)
    if not text.strip():
        return Conventions(data, warnings)
    fm, _, err = parse_document(text)
    if err:
        return Conventions(data, [f"{CONVENTIONS_FILE}: {err}; using defaults"])
    given = fm.get("okf_conventions") or {}
    if not isinstance(given, dict):
        return Conventions(data, ["okf_conventions: must be a mapping; using defaults"])

    for key in sorted(set(given) - set(DEFAULTS)):
        warnings.append(f"okf_conventions.{key}: unknown key, ignored")

    if "types" in given:
        types = given["types"]
        if isinstance(types, dict):
            vocab = {}
            for name, raw in types.items():
                entry = {} if raw is None else raw
                problem = _check_type_entry(name, entry)
                if problem:
                    warnings.append(f"okf_conventions.{problem}; type ignored")
                    continue
                vocab[name] = {
                    "stale_after_days": entry.get("stale_after_days"),
                    "require_human_verified": entry.get("require_human_verified", False),
                }
            data["types"] = vocab
        else:
            warnings.append("okf_conventions.types: must be a mapping; using defaults")

    if "unknown_type" in given:
        if given["unknown_type"] in ("warn", "error"):
            data["unknown_type"] = given["unknown_type"]
        else:
            warnings.append("okf_conventions.unknown_type: must be warn or error; using warn")

    if "lint" in given:
        sub = given["lint"]
        strict = sub.get("strict") if isinstance(sub, dict) else None
        if isinstance(sub, dict) and set(sub) - {"strict"}:
            warnings.append(f"okf_conventions.lint: unknown key(s) {sorted(set(sub) - {'strict'})}, ignored")
        if isinstance(strict, list) and all(r in LINT_RULES for r in strict):
            data["lint"]["strict"] = list(strict)
        else:
            warnings.append(f"okf_conventions.lint.strict: must be a list of rules from {LINT_RULES[0]} "
                            f"to {LINT_RULES[-1]}; using []")

    for section, checks in (
        ("verify", {"allow_self_verify": bool, "require_sha": bool, "bot_git_author": str}),
        ("actors", {k: str for k in DEFAULTS["actors"]}),
    ):
        if section not in given:
            continue
        sub = given[section]
        if not isinstance(sub, dict):
            warnings.append(f"okf_conventions.{section}: must be a mapping; using defaults")
            continue
        for key, value in sub.items():
            if key not in checks:
                warnings.append(f"okf_conventions.{section}.{key}: unknown key, ignored")
                continue
            ok = isinstance(value, checks[key])
            if ok and section == "actors":
                try:
                    re.compile(value)
                except re.error:
                    ok = False
            if ok:
                data[section][key] = value
            else:
                warnings.append(f"okf_conventions.{section}.{key}: invalid value; using default")
    return Conventions(data, warnings)


# ---- frontmatter fields ------------------------------------------------------

def parse_ts(value: Any) -> datetime | None:
    """An ISO 8601 datetime with an explicit offset (§5), else None."""
    s = str(value or "")
    if "T" not in s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def normalize_verified(fm: dict[str, Any]) -> list[dict[str, Any]]:
    """`verified` as a list; a bare mapping is a one-element list (§5.2)."""
    v = fm.get("verified")
    if isinstance(v, dict):
        return [v]
    if isinstance(v, list):
        return [e for e in v if isinstance(e, dict)]
    return []


def trust_tier(fm: dict[str, Any]) -> str:
    """unverified / machine-confirmed / human-reviewed (§5.3)."""
    events = normalize_verified(fm)
    if not events:
        return "unverified"
    if any(str(e.get("by") or "").startswith("human:") for e in events):
        return "human-reviewed"
    return "machine-confirmed"


def is_stale(fm: dict[str, Any], now: datetime) -> bool:
    """now >= stale_after (§5.5). Absent or unparsable values are not stale."""
    stale_after = parse_ts(fm.get("stale_after"))
    return stale_after is not None and now >= stale_after


def latest_verified_at(fm: dict[str, Any], human_only: bool = False) -> datetime | None:
    times = [
        parse_ts(e.get("at"))
        for e in normalize_verified(fm)
        if not human_only or str(e.get("by") or "").startswith("human:")
    ]
    times = [t for t in times if t is not None]
    return max(times) if times else None


def changed_since_verified(fm: dict[str, Any]) -> bool:
    """generated.at is newer than the latest verified[].at (§5.2)."""
    generated = fm.get("generated")
    gen_at = parse_ts(generated.get("at")) if isinstance(generated, dict) else None
    last = latest_verified_at(fm)
    return gen_at is not None and last is not None and gen_at > last


def timestamp_fields(fm: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Every timestamp-valued key OKF v0.2 defines (§5)."""
    generated = fm.get("generated")
    if isinstance(generated, dict) and "at" in generated:
        yield "generated.at", generated["at"]
    for e in normalize_verified(fm):
        if "at" in e:
            yield "verified[].at", e["at"]
    if "stale_after" in fm:
        yield "stale_after", fm["stale_after"]
    for s in fm.get("sources") or []:
        if isinstance(s, dict):
            if "last_modified" in s:
                yield "sources[].last_modified", s["last_modified"]
            for k in ("from", "to"):
                if isinstance(s.get("usage_window"), dict) and k in s["usage_window"]:
                    yield f"sources[].usage_window.{k}", s["usage_window"][k]
    window = fm.get("usage_window")
    if isinstance(window, dict):
        for k in ("from", "to"):
            if k in window:
                yield f"usage_window.{k}", window[k]


def path_fields(fm: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Every path-valued key (§6.2)."""
    if "resource" in fm:
        yield "resource", fm["resource"]
    for s in fm.get("sources") or []:
        if isinstance(s, dict) and "resource" in s:
            yield "sources[].resource", s["resource"]
    if "computation" in fm:
        yield "computation", fm["computation"]
    for key in ("executor", "attester"):
        sub = fm.get(key)
        if isinstance(sub, dict) and "resource" in sub:
            yield f"{key}.resource", sub["resource"]


def actor_fields(fm: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Every actor-valued key (§7, and sources[].author per §5.1)."""
    generated = fm.get("generated")
    if isinstance(generated, dict) and "by" in generated:
        yield "generated.by", generated["by"]
    for e in normalize_verified(fm):
        if "by" in e:
            yield "verified[].by", e["by"]
    for s in fm.get("sources") or []:
        if isinstance(s, dict) and "author" in s:
            yield "sources[].author", s["author"]


def now_utc() -> datetime:
    return datetime.now(UTC)


# ---- /okf verify comments ------------------------------------------------------

_SHA = re.compile(r"^@([0-9a-f]{7,40})$")


def parse_verify_comment(body: str) -> tuple[str | None, list[str]] | None:
    """(sha or None, paths) from a `/okf verify [@<sha>] <path>...` comment.

    Only the first line counts; a trailing CR is dropped. Returns None when the
    comment is not a verify command.
    """
    first = body.split("\n", 1)[0].rstrip("\r").strip()
    words = first.split()
    if words[:2] != ["/okf", "verify"]:
        return None
    rest = words[2:]
    sha = None
    if rest and (m := _SHA.match(rest[0])):
        sha, rest = m.group(1), rest[1:]
    return sha, rest
