from pathlib import Path

from app.chunking import MAX_CHARS, chunk, parse, parse_markdown

SEED = Path(__file__).resolve().parents[2] / "seed"


def test_markdown_headings_become_sections():
    raw = "# Titel\n\nIntro.\n\n## Vakantie\n\n25 dagen.\n\n## Ziekte\n\nBel vóór 9 uur."
    sections = parse_markdown(raw)
    assert [s.heading for s in sections] == ["Titel", "Vakantie", "Ziekte"]
    assert sections[1].text == "25 dagen."


def test_long_paragraph_is_split_under_the_limit():
    sentence = "Dit is een zin van normale lengte om te testen. "
    sections = parse_markdown("## Lang\n\n" + sentence * 40)
    chunks = chunk(sections)
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHARS for c in chunks)
    assert all(c.heading == "Lang" for c in chunks)


def test_every_seed_format_parses_to_chunks():
    for name in ["medewerkershandboek.md", "onboarding.docx", "veiligheid.pdf"]:
        chunks = chunk(parse(SEED / name))
        assert chunks, name


def test_pdf_chunks_carry_page_numbers_and_docx_chunks_carry_headings():
    pdf = chunk(parse(SEED / "veiligheid.pdf"))
    docx = chunk(parse(SEED / "onboarding.docx"))
    assert pdf[0].page == 1
    assert {c.heading for c in docx} >= {"Eerste dag", "Proefperiode"}
