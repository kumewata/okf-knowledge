from datetime import UTC, datetime

import _okf

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def test_conventions_defaults_when_absent(bundle):
    conv = _okf.load_conventions(bundle({"a.md": "---\ntype: Note\n---\n"}))
    assert conv.warnings == []
    assert conv.type_rule("Runbook") == {"stale_after_days": 180, "require_human_verified": False}
    assert conv.data["verify"]["allow_self_verify"] is True


def test_conventions_types_replace_vocabulary(bundle):
    conv = _okf.load_conventions(bundle({"CONVENTIONS.md": """
        ---
        type: OKF Conventions
        okf_conventions:
          types:
            Runbook: { stale_after_days: 30, require_human_verified: true }
            Glossary:
        ---
        """}))
    assert set(conv.types) == {"Runbook", "Glossary"}
    assert conv.type_rule("Runbook") == {"stale_after_days": 30, "require_human_verified": True}
    assert conv.type_rule("Glossary") == {"stale_after_days": None, "require_human_verified": False}


def test_conventions_invalid_value_falls_back(bundle):
    conv = _okf.load_conventions(bundle({"CONVENTIONS.md": """
        ---
        type: OKF Conventions
        okf_conventions:
          unknown_type: explode
          verify: { allow_self_verify: "no", bot_git_author: ci-bot }
          actors: { agent_pattern: "([" }
          types:
            Runbook: { stale_after_days: -1 }
            Note: { stale_after_days: 10 }
          extra: 1
        ---
        """}))
    assert conv.data["unknown_type"] == "warn"
    assert conv.data["verify"] == {"allow_self_verify": True, "require_sha": True, "bot_git_author": "ci-bot"}
    assert conv.data["actors"]["agent_pattern"] == _okf.DEFAULTS["actors"]["agent_pattern"]
    assert set(conv.types) == {"Note"}
    joined = "\n".join(conv.warnings)
    for needle in ("unknown_type", "allow_self_verify", "agent_pattern", "types.Runbook", "extra"):
        assert needle in joined


def test_timestamps_stay_strings(bundle):
    b = bundle({"a.md": "---\ntype: Note\nstale_after: 2026-06-15T00:00:00Z\n---\n"})
    (concept,) = _okf.load_concepts(b)
    assert concept.frontmatter["stale_after"] == "2026-06-15T00:00:00Z"


def test_parse_ts_requires_offset():
    assert _okf.parse_ts("2026-06-15T00:00:00Z") is not None
    assert _okf.parse_ts("2026-06-15T09:00:00+09:00") is not None
    assert _okf.parse_ts("2026-06-15") is None
    assert _okf.parse_ts("2026-06-15T00:00:00") is None


def test_trust_tier_bare_mapping_and_process():
    assert _okf.trust_tier({}) == "unverified"
    assert _okf.trust_tier({"verified": {"by": "human:a", "at": "x"}}) == "human-reviewed"
    assert _okf.trust_tier({"verified": [{"by": "process:n", "at": "x"}]}) == "machine-confirmed"


def test_is_stale_boundary_is_inclusive():
    assert _okf.is_stale({"stale_after": "2026-10-03T00:00:00Z"}, NOW)
    assert not _okf.is_stale({"stale_after": "2026-10-03T00:00:01Z"}, NOW)
    assert not _okf.is_stale({"stale_after": "2026-06-15"}, NOW)


def test_load_concepts_skips_reserved_and_reports_errors(bundle):
    b = bundle({"index.md": "# x\n", "sub/log.md": "# y\n", "a.md": "---\ntype: Note\n", "b.md": "no fm\n"})
    concepts = {c.cid: c for c in _okf.load_concepts(b)}
    assert set(concepts) == {"a", "b"}
    assert concepts["a"].error == "unterminated frontmatter block"
    assert concepts["b"].error == "no frontmatter block"


def test_actor_kind():
    conv = _okf.Conventions(_okf.DEFAULTS)
    assert conv.actor_kind("human:kumewata") == "human"
    assert conv.actor_kind("claude-code/claude-opus-5-5") == "agent"
    assert conv.actor_kind("process:okf-lint") == "process"
    assert conv.actor_kind("team:data-platform") is None
