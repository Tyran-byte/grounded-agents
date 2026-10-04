from pathlib import Path

import pytest

from grounded_agents.core.corpus import Corpus

DATA = Path(__file__).resolve().parents[1] / "data" / "quillmere" / "controls"


def write(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")


def test_parses_sections(tmp_path):
    write(tmp_path, "keys.md", "# Keys\n\n## rotation — Rotation\nKeys rotate yearly.\nLogged.\n\n"
                                "## storage — Storage\nIn a vault.\n")
    corpus = Corpus.load(tmp_path)
    assert corpus.sources() == ["keys#rotation", "keys#storage"]
    section = corpus.get("keys#rotation")
    assert section.title == "Rotation"
    assert section.text == "Keys rotate yearly.\nLogged."


def test_unknown_source_is_none(tmp_path):
    write(tmp_path, "keys.md", "# Keys\n## a — A\ntext\n")
    corpus = Corpus.load(tmp_path)
    assert corpus.get("keys#b") is None
    assert corpus.get("nope#a") is None
    assert corpus.get("no-hash") is None


def test_duplicate_section_id_rejected(tmp_path):
    write(tmp_path, "keys.md", "# Keys\n## a — A\none\n## a — Again\ntwo\n")
    with pytest.raises(ValueError, match="keys#a"):
        Corpus.load(tmp_path)


def test_render_lists_every_section(tmp_path):
    write(tmp_path, "keys.md", "# Keys\n## a — A\none\n")
    assert Corpus.load(tmp_path).render() == "[keys#a] A\none"


def test_bundled_controls_load():
    corpus = Corpus.load(DATA)
    assert len({s.split("#")[0] for s in corpus.sources()}) >= 8
    assert "AES-256" in corpus.get("encryption#at-rest").text
