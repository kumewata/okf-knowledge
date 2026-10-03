import subprocess

import lint

GOOD = """
    ---
    type: Runbook
    generated: { by: claude-code/claude-opus-5-5, at: 2026-10-01T10:00:00+09:00 }
    stale_after: 2027-04-01T00:00:00+09:00
    sources:
      - { id: doc, resource: https://example.com/doc, author: human:alice }
    ---

    # Steps
    """


def rules(findings, level=None):
    return sorted({f.rule for f in findings if level is None or f.level == level})


def test_good_concept_is_clean(bundle):
    assert lint.lint(bundle({"runbooks/a.md": GOOD})) == []


def test_okf001_missing_type(bundle):
    assert rules(lint.lint(bundle({"a.md": "---\ntitle: x\n---\n"}))) == ["OKF001"]


def test_okf001_unterminated_frontmatter(bundle):
    assert rules(lint.lint(bundle({"a.md": "---\ntype: Note\n"}))) == ["OKF001"]


def test_okf001_crlf_is_fine(bundle):
    b = bundle({})
    b.mkdir(parents=True, exist_ok=True)
    (b / "a.md").write_bytes(b"---\r\ntype: Note\r\n---\r\nbody\r\n")
    assert lint.lint(b) == []


def test_okf002_timestamp_without_offset(bundle):
    b = bundle({"a.md": "---\ntype: Note\nstale_after: 2026-06-15\n"
                        "generated: { by: human:a, at: 2026-06-01T00:00:00 }\n---\n"})
    msgs = [f.message for f in lint.lint(b) if f.rule == "OKF002"]
    assert len(msgs) == 2


def test_okf003_relative_path(bundle):
    b = bundle({"a.md": "---\ntype: Note\nsources:\n  - { resource: policies/p.md }\n---\n"})
    assert rules(lint.lint(b)) == ["OKF003"]


def test_okf003_skips_scope_descriptor_and_urls(bundle):
    b = bundle({"a.md": "---\ntype: Note\nresource: https://x.example/t\n"
                        "sources:\n  - { resource: all queries in project X }\n---\n"})
    assert lint.lint(b) == []


def test_okf004_missing_target_is_warning(bundle):
    b = bundle({"a.md": "---\ntype: Note\nsources:\n  - { resource: /policies/p.md }\n---\n"})
    assert rules(lint.lint(b), "warning") == ["OKF004"]
    assert rules(lint.lint(b), "error") == []
    b2 = bundle({"policies/p.md": "---\ntype: Note\n---\n"})
    assert lint.lint(b2) == []


def test_okf005_actor_patterns(bundle):
    b = bundle({"a.md": "---\ntype: Note\ngenerated: { by: gpt, at: 2026-06-01T00:00:00Z }\n"
                        "sources:\n  - { resource: https://x.example, author: team:docs }\n---\n"})
    found = {(f.rule, f.level) for f in lint.lint(b)}
    assert found == {("OKF005", "error"), ("OKF005", "warning")}


def test_okf007_changed_since_verified(bundle):
    b = bundle({"a.md": "---\ntype: Note\ngenerated: { by: human:a, at: 2026-07-01T00:00:00Z }\n"
                        "verified: { by: human:b, at: 2026-06-01T00:00:00Z }\n---\n"})
    assert rules(lint.lint(b)) == ["OKF007"]


def test_okf008_required_human_verification(bundle):
    conv = "---\ntype: OKF Conventions\nokf_conventions:\n  types:\n    Metric: { require_human_verified: true }\n---\n"
    unverified = "---\ntype: Metric\nverified: { by: process:nightly, at: 2026-06-01T00:00:00Z }\n---\n"
    verified = "---\ntype: Metric\nverified: { by: human:b, at: 2026-06-01T00:00:00Z }\n---\n"
    assert rules(lint.lint(bundle({"CONVENTIONS.md": conv, "m.md": unverified}))) == ["OKF008"]
    assert lint.lint(bundle({"CONVENTIONS.md": conv, "m.md": verified})) == []


def test_okf009_unknown_type(bundle):
    assert rules(lint.lint(bundle({"a.md": "---\ntype: Wiki Page\n---\n"})), "warning") == ["OKF009"]
    strict = "---\ntype: OKF Conventions\nokf_conventions: { unknown_type: error }\n---\n"
    b = bundle({"CONVENTIONS.md": strict, "a.md": "---\ntype: Wiki Page\n---\n"})
    assert rules(lint.lint(b), "error") == ["OKF009"]


def test_okf010_index_frontmatter(bundle):
    ok = bundle({"index.md": "---\nokf_version: \"0.2\"\n---\n# x\n", "sub/index.md": "# y\n"})
    assert lint.lint(ok) == []
    bad = bundle({"sub/index.md": "---\nokf_version: \"0.2\"\n---\n# y\n"})
    assert rules(lint.lint(bad)) == ["OKF010"]


def test_conventions_warnings_are_reported(bundle):
    b = bundle({"CONVENTIONS.md": "---\ntype: OKF Conventions\nokf_conventions: { extra: 1 }\n---\n"})
    assert rules(lint.lint(b), "warning") == ["CONV"]


# ---- history rules -----------------------------------------------------------------

def git(repo, *args, author="alice"):
    subprocess.run(["git", "-C", str(repo), "-c", f"user.name={author}", "-c", "user.email=a@example.com",
                    *args], check=True, capture_output=True)


def init_repo(tmp_path, files):
    repo = tmp_path / "knowledge"
    git(tmp_path, "init", "-q", "-b", "main", str(repo))
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "topic")
    return repo


def commit(repo, rel, text, author):
    (repo / rel).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change", author=author)


BASE = "---\ntype: Note\ngenerated: { by: claude-code/m, at: 2026-06-01T00:00:00Z }\n---\nbody\n"
VERIFIED = BASE.replace("---\nbody", "verified:\n  - { by: human:bob, at: 2026-06-02T00:00:00Z }\n---\nbody")


def test_okf006_human_line_by_non_bot(tmp_path):
    repo = init_repo(tmp_path, {"a.md": BASE})
    commit(repo, "a.md", VERIFIED, author="alice")
    found = [f for f in lint.lint(repo, base="main") if f.rule == "OKF006"]
    assert len(found) == 1 and "alice" in found[0].message


def test_okf006_allows_bot(tmp_path):
    repo = init_repo(tmp_path, {"a.md": BASE})
    commit(repo, "a.md", VERIFIED, author="okf-verify[bot]")
    assert rules(lint.lint(repo, base="main")) == []


def test_okf011_content_changed_without_generated(tmp_path):
    repo = init_repo(tmp_path, {"a.md": BASE})
    commit(repo, "a.md", BASE.replace("body", "new body"), author="alice")
    assert rules(lint.lint(repo, base="main")) == ["OKF011"]


def test_okf011_ignores_verified_only_change(tmp_path):
    repo = init_repo(tmp_path, {"a.md": BASE})
    commit(repo, "a.md", VERIFIED, author="okf-verify[bot]")
    assert "OKF011" not in rules(lint.lint(repo, base="main"))


def test_okf011_accepts_regenerated(tmp_path):
    repo = init_repo(tmp_path, {"a.md": BASE})
    commit(repo, "a.md", BASE.replace("body", "new body").replace("06-01T", "06-05T"), author="alice")
    assert rules(lint.lint(repo, base="main")) == []


# ---- review regressions --------------------------------------------------------------

def test_okf006_spaces_and_unicode_names(tmp_path):
    repo = init_repo(tmp_path, {"seed.md": BASE})
    for name in ("my note.md", "café.md"):
        (repo / name).write_text(VERIFIED)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add", author="alice")
    found = sorted(f.path.name for f in lint.lint(repo, base="main") if f.rule == "OKF006")
    assert found == ["café.md", "my note.md"]


def test_okf006_rename_is_not_an_addition(tmp_path):
    repo = init_repo(tmp_path, {"a.md": VERIFIED})
    (repo / "sub").mkdir()
    git(repo, "mv", "a.md", "sub/a.md")
    git(repo, "commit", "-q", "-m", "move", author="alice")
    assert "OKF006" not in rules(lint.lint(repo, base="main"))


def _merge_adding_verification(tmp_path):
    repo = init_repo(tmp_path, {"a.md": BASE, "b.md": BASE})
    git(repo, "checkout", "-q", "-b", "side")
    commit(repo, "b.md", BASE.replace("body", "side body").replace("06-01T", "06-03T"), author="alice")
    git(repo, "checkout", "-q", "topic")
    git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    (repo / "a.md").write_text(VERIFIED)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "merge", author="alice")
    return repo


def test_okf006_merge_commit_is_checked(tmp_path):
    repo = _merge_adding_verification(tmp_path)
    assert rules(lint.lint(repo, base="main")) == ["OKF006"]
    assert rules(lint.lint(repo, base="main", attestations=[])) == ["OKF006"]


def test_okf006_forged_bot_author_fails_against_comments(tmp_path):
    repo = init_repo(tmp_path, {"a.md": BASE})
    commit(repo, "a.md", VERIFIED, author="okf-verify[bot]")
    assert lint.lint(repo, base="main") == []  # the local fallback trusts the author name
    assert rules(lint.lint(repo, base="main", attestations=[])) == ["OKF006"]


COMMENT = {"body": "/okf verify @abc1234 a.md\r\nthanks", "user": {"login": "bob"},
           "created_at": "2026-06-02T00:00:00Z"}


def test_attestations_from_comments():
    a = lint.attestations_from_comments([COMMENT], writers={"bob"}, excluded=set())
    assert a == [lint.Attestation("human:bob", "2026-06-02T00:00:00Z", frozenset({"a.md"}))]
    assert lint.attestations_from_comments([COMMENT], writers={"alice"}, excluded=set()) == []
    assert lint.attestations_from_comments([COMMENT], writers={"bob"}, excluded={"bob"}) == []
    other = {**COMMENT, "body": "LGTM"}
    assert lint.attestations_from_comments([other], writers={"bob"}, excluded=set()) == []


def test_okf006_matches_comment_exactly(tmp_path):
    repo = init_repo(tmp_path, {"a.md": BASE})
    commit(repo, "a.md", VERIFIED, author="okf-verify[bot]")
    ok = lint.Attestation("human:bob", "2026-06-02T00:00:00Z", frozenset({"a.md"}))
    assert lint.lint(repo, base="main", attestations=[ok]) == []
    for bad in (lint.Attestation("human:bob", "2026-06-02T00:00:01Z", frozenset({"a.md"})),
                lint.Attestation("human:eve", "2026-06-02T00:00:00Z", frozenset({"a.md"})),
                lint.Attestation("human:bob", "2026-06-02T00:00:00Z", frozenset({"b.md"}))):
        assert rules(lint.lint(repo, base="main", attestations=[bad])) == ["OKF006"]


def test_conventions_from_base_ignore_pr_changes(tmp_path):
    loose = "---\ntype: OKF Conventions\nokf_conventions:\n  verify: { bot_git_author: alice }\n---\n"
    repo = init_repo(tmp_path, {"a.md": BASE})
    (repo / "CONVENTIONS.md").write_text(loose)
    commit(repo, "a.md", VERIFIED, author="alice")
    assert "OKF006" not in rules(lint.lint(repo, base="main"))
    assert "OKF006" in rules(lint.lint(repo, base="main", conventions_text=""))


def test_okf011_skips_conventions_file(tmp_path):
    conv = "---\ntype: OKF Conventions\nokf_conventions: {}\n---\n"
    repo = init_repo(tmp_path, {"CONVENTIONS.md": conv})
    commit(repo, "CONVENTIONS.md", conv + "\nrules\n", author="alice")
    assert "OKF011" not in rules(lint.lint(repo, base="main"))


def test_bad_base_exits_2(tmp_path, monkeypatch, capsys):
    repo = init_repo(tmp_path, {"a.md": BASE})
    monkeypatch.setattr("sys.argv", ["lint.py", str(repo), "--base", "nope"])
    assert lint.main() == 2
    assert "error: git" in capsys.readouterr().err


def test_hidden_directories_are_skipped(bundle):
    b = bundle({"a.md": "---\ntype: Note\n---\n", ".okf-knowledge/x.md": "no frontmatter\n"})
    assert lint.lint(b) == []


def test_bom_and_invalid_utf8(bundle):
    b = bundle({})
    b.mkdir(parents=True, exist_ok=True)
    (b / "bom.md").write_bytes("﻿---\ntype: Note\n---\n".encode())
    (b / "latin1.md").write_bytes(b"---\ntype: Caf\xe9\n---\n")
    found = {(f.path.name, f.rule) for f in lint.lint(b)}
    assert found == {("latin1.md", "OKF001")}
