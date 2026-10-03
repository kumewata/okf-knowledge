from datetime import UTC, datetime
from pathlib import Path

import status

MINI = Path(__file__).parent / "fixtures" / "mini"
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def test_status_matches_explainer_mini():
    """Same 7 concepts and the same verdicts as the OKF v0.2 explainer's survey."""
    rows = {r["cid"]: r for r in status.classify(MINI, NOW)}
    got = {cid: (r["status"], r["tier"], r["stale"]) for cid, r in rows.items() if not r["unreadable"]}
    assert got == {
        "computations/custom": ("stable", "unverified", False),
        "metrics/bare": ("stable", "unverified", False),
        "metrics/dateonly": ("stable", "unverified", False),
        "metrics/legacy": ("deprecated", "human-reviewed", False),
        "metrics/nightly": ("stable", "machine-confirmed", True),
        "metrics/signed": ("stable", "human-reviewed", False),
    }
    assert rows["computations/broken"]["unreadable"]


def test_status_markdown_sections():
    md = status.to_markdown(status.classify(MINI, NOW), NOW)
    assert "## Stale (1)\n\n- [nightly](/metrics/nightly.md) — machine-confirmed, stale_after 2026-06-15T00:00:00Z" in md
    assert "## Deprecated (1)" in md
    assert "## Unverified (3)" in md
    # nightly: generated.at 06-14 is newer than its only verification on 06-12
    assert "## Changed since verification (1)\n\n- [nightly](/metrics/nightly.md)" in md
    assert "## Unreadable (1)\n\n- [type を書き忘れた](/computations/broken.md)" in md


def test_status_markdown_empty_section(bundle):
    b = bundle({"a.md": "---\ntype: Note\n---\n"})
    md = status.to_markdown(status.classify(b, NOW), NOW)
    assert "## Stale (0)\n\n_none_" in md
