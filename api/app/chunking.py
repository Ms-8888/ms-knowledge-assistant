import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

MAX_CHARS = 800
SUPPORTED = {".md", ".pdf", ".docx"}


@dataclass
class Section:
    heading: str | None
    page: int | None
    text: str


@dataclass
class ChunkData:
    heading: str | None
    page: int | None
    text: str


def parse_markdown(raw: str) -> list[Section]:
    sections: list[Section] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(Section(heading, None, body))
        buffer.clear()

    for line in raw.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*)", line)
        if match:
            flush()
            heading = match.group(2).strip()
        else:
            buffer.append(line)
    flush()
    return sections


def parse_docx(path: Path) -> list[Section]:
    sections: list[Section] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(Section(heading, None, body))
        buffer.clear()

    for paragraph in DocxDocument(str(path)).paragraphs:
        if paragraph.style is not None and paragraph.style.name.startswith("Heading"):
            flush()
            heading = paragraph.text.strip()
        elif paragraph.text.strip():
            buffer.append(paragraph.text.strip())
    flush()
    return sections


def parse_pdf(path: Path) -> list[Section]:
    sections = []
    for number, page in enumerate(PdfReader(str(path)).pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            sections.append(Section(None, number, text))
    return sections


def parse(path: Path) -> list[Section]:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return parse_markdown(path.read_text(encoding="utf-8"))
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _hard_wrap(text: str) -> list[str]:
    """Split a piece that is still too long at spaces; cut inside a word only as a last resort."""
    pieces: list[str] = []
    current = ""
    for word in text.split(" "):
        while len(word) > MAX_CHARS:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:MAX_CHARS])
            word = word[MAX_CHARS:]
        if current and len(current) + len(word) + 1 > MAX_CHARS:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def _split_long(paragraph: str) -> list[str]:
    sentences = [
        part
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
        for part in (_hard_wrap(sentence) if len(sentence) > MAX_CHARS else [sentence])
    ]
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > MAX_CHARS:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def chunk(sections: list[Section]) -> list[ChunkData]:
    chunks: list[ChunkData] = []
    for section in sections:
        units: list[str] = []
        for paragraph in section.text.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            units.extend(_split_long(paragraph) if len(paragraph) > MAX_CHARS else [paragraph])
        current = ""
        for unit in units:
            if current and len(current) + len(unit) + 1 > MAX_CHARS:
                chunks.append(ChunkData(section.heading, section.page, current))
                current = unit
            else:
                current = f"{current} {unit}".strip()
        if current:
            chunks.append(ChunkData(section.heading, section.page, current))
    return chunks
