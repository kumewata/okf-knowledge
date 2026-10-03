import textwrap
from pathlib import Path

import pytest


def write_bundle(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return root


@pytest.fixture
def bundle(tmp_path):
    """Return a factory that writes {relative path: text} into a fresh bundle."""
    return lambda files: write_bundle(tmp_path / "knowledge", files)
