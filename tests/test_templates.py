import inspect
import re
import shutil
from pathlib import Path

import _okf
import lint
import pytest
import yaml

TEMPLATES = Path(__file__).parents[1] / "skills" / "okf-knowledge" / "templates"
TYPE_TEMPLATES = sorted(p for p in TEMPLATES.glob("*.md") if p.name != "CONVENTIONS.md")
FILL = {
    "<AGENT>": "claude-code/claude-opus-5-5",
    "<NOW>": "2026-10-03T14:00:00+09:00",
    "<STALE_AFTER>": "2027-04-01T00:00:00+09:00",
    "<TABLE_URL>": "https://console.cloud.google.com/bigquery?p=acme&d=sales&t=orders",
    "<SOURCE_URL>": "https://example.com/doc",
}


def fill(text):
    for k, v in FILL.items():
        text = text.replace(k, v)
    return text


def test_conventions_template_equals_defaults(tmp_path):
    shutil.copy(TEMPLATES / "CONVENTIONS.md", tmp_path / "CONVENTIONS.md")
    conv = _okf.load_conventions(tmp_path)
    assert conv.warnings == []
    assert conv.data == _okf.DEFAULTS


@pytest.mark.parametrize("template", TYPE_TEMPLATES, ids=lambda p: p.stem)
def test_filled_template_is_clean(tmp_path, template):
    shutil.copy(TEMPLATES / "CONVENTIONS.md", tmp_path / "CONVENTIONS.md")
    (tmp_path / template.name).write_text(fill(template.read_text()))
    assert lint.lint(tmp_path) == []


@pytest.mark.parametrize("template", TYPE_TEMPLATES, ids=lambda p: p.stem)
def test_unfilled_template_is_caught(tmp_path, template):
    shutil.copy(template, tmp_path / template.name)
    found = {f.rule for f in lint.lint(tmp_path) if f.level == "error"}
    assert {"OKF002", "OKF005"} <= found


def test_schema_doc_matches_defaults():
    doc = (TEMPLATES.parent / "references" / "conventions-schema.md").read_text()
    block = re.search(r"```yaml\n(.*?)```", doc, re.DOTALL).group(1)
    assert yaml.safe_load(block) == _okf.DEFAULTS


def test_schema_doc_lists_every_lint_rule():
    doc = (TEMPLATES.parent / "references" / "conventions-schema.md").read_text()
    used = set(re.findall(r'"(OKF\d{3}|CONV)"', inspect.getsource(lint)))
    listed = set(re.findall(r"^\| (OKF\d{3}|CONV) \|", doc, re.MULTILINE))
    assert used == listed

