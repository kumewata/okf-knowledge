import index

FILES = {
    "runbooks/restart.md": "---\ntype: Runbook\ntitle: Restart the API\ndescription: |\n  How to restart\n  safely.\n---\n",
    "runbooks/notitle.md": "---\ntype: Runbook\n---\n",
    "glossary.md": "---\ntype: Glossary\ntitle: Terms\n---\n",
    "empty/.keep.md": "",
}


def write(b):
    for path, text in index.render_indexes(b).items():
        if text is not None:
            path.write_text(text)


def test_index_renders_concepts_then_subdirectories(bundle):
    b = bundle(FILES)
    rendered = {p.relative_to(b).as_posix(): t for p, t in index.render_indexes(b).items()}
    assert set(rendered) == {"index.md", "runbooks/index.md"}
    assert rendered["runbooks/index.md"] == (
        "# runbooks\n\n"
        "* [notitle](notitle.md)\n"
        "* [Restart the API](restart.md) - How to restart safely.\n"
    )
    assert rendered["index.md"] == "# knowledge\n\n* [Terms](glossary.md)\n* [runbooks](runbooks/index.md)\n"


def test_index_check_detects_drift(bundle, capsys, monkeypatch):
    b = bundle(FILES)
    write(b)
    monkeypatch.setattr("sys.argv", ["index.py", str(b), "--check"])
    assert index.main() == 0
    (b / "runbooks/new.md").write_text("---\ntype: Runbook\ntitle: New\n---\n")
    assert index.main() == 1
    assert "runbooks/index.md" in capsys.readouterr().out


def test_index_keeps_root_okf_version(bundle):
    b = bundle({**FILES, "index.md": '---\nokf_version: "0.2"\n---\n\n# old\n'})
    write(b)
    text = (b / "index.md").read_text()
    assert text.startswith('---\nokf_version: "0.2"\n---\n\n# knowledge\n')
    assert "# old" not in text


def test_index_check_detects_orphaned_index(bundle, monkeypatch):
    b = bundle({"sub/c.md": "---\ntype: Note\n---\n", "top.md": "---\ntype: Note\n---\n"})
    write(b)
    (b / "sub/c.md").unlink()
    monkeypatch.setattr("sys.argv", ["index.py", str(b), "--check"])
    assert index.main() == 1
    monkeypatch.setattr("sys.argv", ["index.py", str(b)])
    assert index.main() == 0
    assert not (b / "sub/index.md").exists()


def test_index_root_heading_for_dot(bundle, monkeypatch):
    b = bundle({"a.md": "---\ntype: Note\n---\n"})
    monkeypatch.chdir(b)
    from pathlib import Path
    (text,) = [t for p, t in index.render_indexes(Path(".")).items()]
    assert text.startswith("# knowledge\n")


def test_index_links_with_spaces(bundle):
    b = bundle({"my note.md": "---\ntype: Note\n---\n"})
    (text,) = index.render_indexes(b).values()
    assert "* [my note](<my note.md>)" in text


def test_index_never_removes_root(bundle):
    b = bundle({"index.md": '---\nokf_version: "0.2"\n---\n'})
    assert index.render_indexes(b) == {}
