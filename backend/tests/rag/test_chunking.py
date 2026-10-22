from collections import Counter

from backend.rag.chunking import (
    Chunk,
    balanced_groups,
    chunk_document,
    chunk_provision,
    estimate_tokens,
)
from backend.rag.parsing import Block, ParsedDocument, own_lines, parse_document

MAX_TOKENS = 500


def refs(chunks: list[Chunk], key: str | None = None) -> list[str]:
    return [chunk.ref for chunk in chunks if key is None or chunk.provision_key == key]


def chapeaux(block: Block, depth: int = 0) -> list[str]:
    """Own lines of every block that has children: the only lines chunks may repeat."""
    if not block.children:
        return []
    lines = own_lines(block, depth)
    for child in block.children:
        lines += chapeaux(child, depth + 1 if block.label else depth)
    return lines


def test_balanced_groups() -> None:
    # Paragraph sizes of Article 53: filling greedily would leave paragraph 7 alone.
    assert balanced_groups([376, 118, 52, 156, 77, 41, 47], 500) == [
        [0],
        [1, 2, 3, 4, 5, 6],
    ]
    assert balanced_groups([54, 245, 85, 96, 101, 186, 82, 59, 165], 500) == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
    ]
    assert balanced_groups([600, 50], 500) == [[0], [1]]
    assert balanced_groups([100], 500) == [[0]]


def test_chapter_chunks(chapter_v: str) -> None:
    chunks = chunk_document(parse_document(chapter_v), MAX_TOKENS)

    assert refs(chunks) == [
        "Article 51",
        "Article 52(1)–(3)",
        "Article 52(4)–(6)",
        "Article 53(1)",
        "Article 53(2)–(7)",
        "Article 54(1)–(3)",
        "Article 54(4)–(6)",
        "Article 55",
        "Article 56(1)–(3)",
        "Article 56(4)–(6)",
        "Article 56(7)–(9)",
    ]
    article_53 = chunks[3]
    assert article_53.provision_key == "article:53"
    assert article_53.text.startswith(
        "1. Providers of general-purpose AI models shall:\n  (a) draw up"
    )
    assert article_53.embedding_text == f"{article_53.header}\n\n{article_53.text}"


def test_annex_chunks_repeat_the_chapeaux(annex_iv: str) -> None:
    chunks = chunk_document(parse_document(annex_iv), MAX_TOKENS)

    assert refs(chunks) == [
        "Annex IV, point 1",
        "Annex IV, point 2(a)–(c)",
        "Annex IV, point 2(d)–(h)",
        "Annex IV, points 3–9",
    ]
    intro = "The technical documentation referred to in Article 11(1) shall contain"
    assert all(chunk.text.startswith(intro) for chunk in chunks)
    assert (
        chunks[2]
        .text.splitlines()[1]
        .startswith("2. A detailed description of the elements of the AI system")
    )


def test_one_chunk_per_definition(ai_act: dict[str, ParsedDocument]) -> None:
    chunks = chunk_document(ai_act["CHAPTER I"], MAX_TOKENS)

    assert refs(chunks, "article:3") == [f"Article 3({n})" for n in range(1, 69)]
    definitions = [chunk for chunk in chunks if chunk.provision_key == "article:3"]
    assert all(
        chunk.text.startswith(
            "For the purposes of this Regulation, the following definitions apply:\n("
        )
        for chunk in definitions
    )


def test_points_repeat_their_paragraph(ai_act: dict[str, ParsedDocument]) -> None:
    chunks = chunk_document(ai_act["CHAPTER II"], MAX_TOKENS)

    assert refs(chunks) == [
        "Article 5(1)(a)–(c)",
        "Article 5(1)(d)–(g)",
        "Article 5(1)(h)",
        "Article 5(2)",
        "Article 5(3)",
        "Article 5(4)–(5)",
        "Article 5(6)–(8)",
    ]
    assert all(
        chunk.text.startswith("1. The following AI practices shall be prohibited:\n")
        for chunk in chunks[:3]
    )


def test_annex_refs(ai_act: dict[str, ParsedDocument]) -> None:
    assert refs(chunk_document(ai_act["ANNEX VII"], MAX_TOKENS)) == [
        "Annex VII, points 1–2",
        "Annex VII, point 3",
        "Annex VII, points 4.1–4.4",
        "Annex VII, point 4.5",
        "Annex VII, point 4.6",
        "Annex VII, point 4.7",
        "Annex VII, point 5",
    ]
    assert refs(chunk_document(ai_act["ANNEX XI"], MAX_TOKENS)) == [
        "Annex XI, Section 1, point 1",
        "Annex XI, Section 1, point 2",
        "Annex XI, Section 2",
    ]


def test_chunks_respect_the_budget(ai_act: dict[str, ParsedDocument]) -> None:
    over_budget = [
        chunk.ref
        for document in ai_act.values()
        for chunk in chunk_document(document, MAX_TOKENS)
        if estimate_tokens(chunk.text) > MAX_TOKENS
    ]

    # A single paragraph of seven subparagraphs and no points: it cannot be split.
    assert over_budget == ["Article 26(10)"]


def test_chunks_cover_each_provision_once(ai_act: dict[str, ParsedDocument]) -> None:
    for document in ai_act.values():
        for provision in document.provisions:
            chunks = chunk_provision(provision, MAX_TOKENS)
            provision_lines = Counter(provision.text.splitlines())
            chunk_lines = Counter(
                line for chunk in chunks for line in chunk.text.splitlines()
            )

            assert not provision_lines - chunk_lines, provision.label
            repeated = chunk_lines - provision_lines
            assert set(repeated) <= set(chapeaux(provision.root)), provision.label
            assert {chunk.header for chunk in chunks} == {provision.header}
