import subprocess

import _okf
import pytest
import verify

BY, AT = "human:bob", "2026-10-03T05:00:00Z"
CONV = _okf.Conventions(_okf.DEFAULTS)
HEAD = "---\ntype: Note\n# a comment that must survive\ngenerated: { by: claude-code/m, at: 2026-10-01T10:00:00+09:00 }\n"


def run(b, *names, by=BY, at=AT):
    return verify.plan(b, b, [str(b / n) for n in names], by, at, CONV)


def verified_of(text):
    fm, _, _ = _okf.parse_document(text)
    return _okf.normalize_verified(fm)


def test_verify_appends_to_list(bundle):
    text = HEAD + "verified:\n  - { by: process:nightly, at: 2026-09-01T00:00:00Z }\nstale_after: 2027-01-01T00:00:00Z\n---\nbody\n"
    b = bundle({"a.md": text})
    (_, new), = run(b, "a.md")
    assert new == text.replace("Z }\nstale", f"Z }}\n  - {{ by: {BY}, at: {AT} }}\nstale")


def test_verify_appends_to_block_style_list(bundle):
    text = HEAD + "verified:\n- by: process:nightly\n  at: 2026-09-01T00:00:00Z\n---\n"
    b = bundle({"a.md": text})
    (_, new), = run(b, "a.md")
    assert [e["by"] for e in verified_of(new)] == ["process:nightly", BY]


def test_verify_converts_bare_mapping(bundle):
    flow = HEAD + "verified: { by: human:alice, at: 2026-09-01T00:00:00Z }\n---\n"
    block = HEAD + "verified:\n  by: human:alice\n  at: 2026-09-01T00:00:00Z\n---\n"
    b = bundle({"flow.md": flow, "block.md": block})
    for (_, new) in run(b, "flow.md", "block.md"):
        assert verified_of(new) == [{"by": "human:alice", "at": "2026-09-01T00:00:00Z"}, {"by": BY, "at": AT}]


def test_verify_creates_block_when_absent(bundle):
    b = bundle({"a.md": HEAD + "---\nbody\n"})
    (_, new), = run(b, "a.md")
    assert new == HEAD + f"verified:\n  - {{ by: {BY}, at: {AT} }}\n---\nbody\n"


def test_verify_is_idempotent(bundle):
    b = bundle({"a.md": HEAD + f"verified:\n  - {{ by: {BY}, at: {AT} }}\n---\n"})
    assert run(b, "a.md") == [((b / "a.md").resolve(), None)]


def test_verify_preserves_other_lines(bundle):
    text = HEAD + "tags: [a, 'b']\nverified:\n  - { by: human:alice, at: 2026-09-01T00:00:00Z }\nsources:\n  - { id: x, resource: https://e.example }\n---\n# Body\n\ntext\n"
    b = bundle({"a.md": text})
    (_, new), = run(b, "a.md")
    added = [ln for ln in new.splitlines() if ln not in text.splitlines()]
    assert added == [f"  - {{ by: {BY}, at: {AT} }}"]
    assert new.replace(added[0] + "\n", "") == text


def test_verify_preserves_crlf(bundle):
    b = bundle({})
    b.mkdir(parents=True, exist_ok=True)
    text = "---\r\ntype: Note\r\nverified:\r\n  - { by: human:a, at: 2026-09-01T00:00:00Z }\r\n---\r\nbody\r\n"
    (b / "a.md").write_bytes(text.encode())
    (_, new), = run(b, "a.md")
    assert new == text.replace("Z }\r\n---", f"Z }}\r\n  - {{ by: {BY}, at: {AT} }}\r\n---")


def test_verify_rejects_outside_bundle(bundle, tmp_path):
    b = bundle({"a.md": HEAD + "---\n"})
    (tmp_path / "outside.md").write_text(HEAD + "---\n")
    with pytest.raises(ValueError, match="outside"):
        verify.plan(b, b, [str(tmp_path / "outside.md")], BY, AT, CONV)
    with pytest.raises(ValueError, match=r"\.\."):
        verify.plan(b, b, [str(b / ".." / "outside.md")], BY, AT, CONV)
    with pytest.raises(ValueError, match="not a concept"):
        verify.plan(b, b, [str(b / "index.md")], BY, AT, CONV)


def test_verify_rejects_non_human_actor(bundle):
    b = bundle({"a.md": HEAD + "---\n"})
    for by in ("claude-code/m", "process:okf-verify", "human:bad id"):
        with pytest.raises(ValueError, match="not a human actor"):
            run(b, "a.md", by=by)


def test_verify_rejects_naive_timestamp(bundle):
    b = bundle({"a.md": HEAD + "---\n"})
    for at in ("2026-10-03", "2026-10-03T05:00:00"):
        with pytest.raises(ValueError, match="offset"):
            run(b, "a.md", at=at)


def test_verify_all_or_nothing(bundle, monkeypatch, capsys):
    b = bundle({"a.md": HEAD + "---\n"})
    before = (b / "a.md").read_text()
    monkeypatch.setattr("sys.argv", ["verify.py", str(b), str(b / "a.md"), str(b / "missing.md"),
                                     "--by", BY, "--at", AT])
    assert verify.main() == 2
    assert (b / "a.md").read_text() == before


def test_verify_rejects_unsupported_layout(bundle):
    b = bundle({"a.md": HEAD + "verified: [ { by: human:a, at: 2026-09-01T00:00:00Z } ]\n---\n"})
    with pytest.raises(verify.Unsupported, match="flow sequence"):
        run(b, "a.md")


def test_verify_self_verify_disabled(bundle):
    b = bundle({"a.md": HEAD + "---\n"})
    strict = _okf.Conventions({**_okf.DEFAULTS, "verify": {**_okf.DEFAULTS["verify"], "allow_self_verify": False}})
    with pytest.raises(ValueError, match="self-verification"):
        verify.plan(b, b, [str(b / "a.md")], BY, AT, strict, pr_authors={"bob"})
    assert verify.plan(b, b, [str(b / "a.md")], BY, AT, strict, pr_authors={"alice"})[0][1] is not None
    assert verify.plan(b, b, [str(b / "a.md")], BY, AT, CONV, pr_authors={"bob"})[0][1] is not None


def test_verify_commit_passes_lint_history(tmp_path, monkeypatch):
    """End to end: a verify commit by the bot does not trip OKF006 or OKF011."""
    import lint
    from test_lint import BASE, init_repo

    repo = init_repo(tmp_path, {"a.md": BASE})
    monkeypatch.setattr("sys.argv", ["verify.py", str(repo), str(repo / "a.md"), "--by", BY, "--at", AT, "--commit"])
    assert verify.main() == 0
    assert lint.lint(repo, base="main") == []
    author = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%an"],
                            capture_output=True, text=True, check=True).stdout
    assert author.strip() == "okf-verify[bot]"



def test_paths_relative_to_repo_root_and_changed_only(bundle):
    b = bundle({"a.md": HEAD + "---\n", "b.md": HEAD + "---\n"})
    repo = b.parent
    changes = verify.plan(repo, b, ["knowledge/a.md"], BY, AT, CONV, changed={"knowledge/a.md"})
    assert changes[0][0] == (b / "a.md").resolve()
    with pytest.raises(ValueError, match="not changed by this pull request"):
        verify.plan(repo, b, ["knowledge/b.md"], BY, AT, CONV, changed={"knowledge/a.md"})


def test_paths_from_comment_sha_rules():
    body = "/okf verify @abc1234 knowledge/a.md knowledge/b.md\r\nthanks"
    assert verify.paths_from_comment(body, "abc1234ffff", CONV) == ["knowledge/a.md", "knowledge/b.md"]
    with pytest.raises(ValueError, match="not the pull request's head"):
        verify.paths_from_comment(body, "def5678", CONV)
    with pytest.raises(ValueError, match="name the commit"):
        verify.paths_from_comment("/okf verify knowledge/a.md", "abc1234", CONV)
    loose = _okf.Conventions({**_okf.DEFAULTS, "verify": {**_okf.DEFAULTS["verify"], "require_sha": False}})
    assert verify.paths_from_comment("/okf verify knowledge/a.md\r", "abc1234", loose) == ["knowledge/a.md"]
    with pytest.raises(ValueError, match="not `/okf verify"):
        verify.paths_from_comment("LGTM", "abc", CONV)


def test_main_uses_base_conventions_and_comment(bundle, tmp_path, monkeypatch, capsys):
    b = bundle({"a.md": HEAD + "---\n",
                "CONVENTIONS.md": "---\ntype: OKF Conventions\nokf_conventions:\n  verify: { allow_self_verify: true }\n---\n"})
    base_conv = tmp_path / "base.md"
    base_conv.write_text("---\ntype: OKF Conventions\nokf_conventions:\n  verify: { allow_self_verify: false }\n---\n")
    comment = tmp_path / "comment.txt"
    comment.write_text("/okf verify @abc1234 knowledge/a.md\n")
    argv = ["verify.py", str(b), "--comment", str(comment), "--head-sha", "abc1234def", "--repo-root", str(b.parent),
            "--by", BY, "--at", AT, "--pr-authors", "alice,bob"]
    monkeypatch.setattr("sys.argv", argv + ["--conventions", str(base_conv)])
    assert verify.main() == 2
    assert "disallow self-verification" in capsys.readouterr().err
    monkeypatch.setattr("sys.argv", argv)  # the PR's own conventions would have allowed it
    assert verify.main() == 0


def test_verify_crlf_body_does_not_change_lf_frontmatter(bundle):
    b = bundle({})
    b.mkdir(parents=True, exist_ok=True)
    (b / "a.md").write_bytes(b"---\ntype: Note\n---\nbody\r\n")
    (_, new), = run(b, "a.md")
    assert "\r" not in new.split("---", 2)[1]


def test_verify_keeps_bom_and_rejects_invalid_utf8(bundle):
    b = bundle({})
    b.mkdir(parents=True, exist_ok=True)
    (b / "bom.md").write_bytes("\ufeff---\ntype: Note\n---\n".encode())
    (b / "latin1.md").write_bytes(b"---\ntype: Caf\xe9\n---\n")
    (_, new), = run(b, "bom.md")
    assert new.startswith("\ufeff---\n") and BY in new
    with pytest.raises(ValueError, match="UTF-8"):
        run(b, "latin1.md")
