"""The fact base: markdown control documents addressed as ``<doc>#<section-id>``.

A document is ``# Title`` followed by sections headed ``## <id> — <Title>``. Small on purpose:
the whole corpus fits in a prompt, so there is no retrieval step that could silently drop the
passage that matters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^## (?P<id>[a-z0-9-]+) — (?P<title>.+?)\s*$")


@dataclass(frozen=True)
class Section:
    source: str
    title: str
    text: str


class Corpus:
    def __init__(self, sections: dict[str, Section]):
        self._sections = dict(sections)

    @classmethod
    def load(cls, directory: Path | str) -> "Corpus":
        sections: dict[str, Section] = {}
        for path in sorted(Path(directory).glob("*.md")):
            for section in _parse(path.stem, path.read_text(encoding="utf-8")):
                if section.source in sections:
                    raise ValueError(f"duplicate section {section.source}")
                sections[section.source] = section
        return cls(sections)

    def get(self, source: str) -> Section | None:
        return self._sections.get(source)

    def sources(self) -> list[str]:
        return list(self._sections)

    def render(self) -> str:
        return "\n\n".join(f"[{s.source}] {s.title}\n{s.text}" for s in self._sections.values())


def _parse(doc: str, text: str) -> list[Section]:
    sections: list[Section] = []
    current: tuple[str, str] | None = None
    lines: list[str] = []

    def flush() -> None:
        if current is not None:
            sections.append(Section(f"{doc}#{current[0]}", current[1], "\n".join(lines).strip()))

    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            current, lines = (match["id"], match["title"]), []
        elif current is not None:
            lines.append(line)
    flush()
    return sections
