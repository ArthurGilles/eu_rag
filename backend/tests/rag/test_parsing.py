import re

import pytest

from backend.models.document import DocumentKind
from backend.rag.parsing import (
    Block,
    ParsedDocument,
    ParseError,
    Provision,
    parse_document,
    read_header,
)


def labels(block: Block) -> list[str | None]:
    return [child.label for child in block.children]


def provision(document: ParsedDocument, key: str) -> Provision:
    return next(provision for provision in document.provisions if provision.key == key)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CHAPTER V\n\nGENERAL-PURPOSE AI MODELS", (DocumentKind.chapter, 5)),
        ("\n\nANNEX XIII  \n\nCriteria", (DocumentKind.annex, 13)),
        ("CHAPTER IV", (DocumentKind.chapter, 4)),
        ("CHAPTER IIII\n", None),
        ("CHAPTER 5\n", None),
        ("CHAPTER V GENERAL\n", None),
        ("Article 5\n", None),
        ("Some text\nCHAPTER V\n", None),
    ],
)
def test_read_header(text: str, expected: tuple[DocumentKind, int] | None) -> None:
    assert read_header(text) == expected


def test_chapter(chapter_v: str) -> None:
    document = parse_document(chapter_v)

    assert (document.kind, document.number) == (DocumentKind.chapter, 5)
    assert document.title == "GENERAL-PURPOSE AI MODELS"
    assert document.doc_key == "chapter:V"
    assert [p.key for p in document.provisions] == [
        f"article:{n}" for n in range(51, 57)
    ]
    article_53 = provision(document, "article:53")
    assert article_53.label == "Article 53"
    assert article_53.title == "Obligations for providers of general-purpose AI models"
    assert article_53.header == (
        "Chapter V — GENERAL-PURPOSE AI MODELS"
        " › Section 2 — Obligations for providers of general-purpose AI models"
        " › Article 53 — Obligations for providers of general-purpose AI models"
    )
    assert labels(article_53.root) == [f"{n}." for n in range(1, 8)]
    paragraph_1 = article_53.root.children[0]
    assert paragraph_1.lines == ["Providers of general-purpose AI models shall:"]
    assert labels(paragraph_1) == ["(a)", "(b)", "(c)", "(d)"]
    assert labels(paragraph_1.children[1]) == ["(i)", "(ii)"]
    assert paragraph_1.children[1].children[0].family == "roman"


def test_unnumbered_subparagraph_stays_in_its_paragraph(chapter_v: str) -> None:
    paragraph_4 = provision(parse_document(chapter_v), "article:52").root.children[3]

    assert paragraph_4.label == "4."
    assert len(paragraph_4.lines) == 2
    assert paragraph_4.lines[1].startswith("The Commission is empowered")


def test_annex(annex_iv: str) -> None:
    document = parse_document(annex_iv)

    assert (document.kind, document.number) == (DocumentKind.annex, 4)
    (annex,) = document.provisions
    assert (annex.key, annex.label) == ("annex:IV", "Annex IV")
    assert annex.header == (
        "Annex IV — Technical documentation referred to in Article 11(1)"
    )
    assert annex.root.lines[0].startswith(
        "The technical documentation referred to in Article 11(1) shall contain"
    )
    assert labels(annex.root) == [f"{n}." for n in range(1, 10)]
    assert labels(annex.root.children[0]) == [f"({c})" for c in "abcdefgh"]


def test_whole_regulation(ai_act: dict[str, ParsedDocument]) -> None:
    documents = list(ai_act.values())

    assert len(documents) == 26
    assert [p.key for d in documents for p in d.provisions if p.is_article] == [
        f"article:{n}" for n in range(1, 114)
    ]
    assert [
        p.key for d in documents if d.kind is DocumentKind.annex for p in d.provisions
    ] == [
        "annex:I:A",
        "annex:I:B",
        "annex:II",
        "annex:III",
        "annex:IV",
        "annex:V",
        "annex:VI",
        "annex:VII",
        "annex:VIII:A",
        "annex:VIII:B",
        "annex:VIII:C",
        "annex:IX",
        "annex:X",
        "annex:XI:1",
        "annex:XI:2",
        "annex:XII",
        "annex:XIII",
    ]


def test_escapes_and_links_are_removed(ai_act: dict[str, ParsedDocument]) -> None:
    for document in ai_act.values():
        for p in document.provisions:
            assert "\\" not in p.text
            assert "](" not in p.text
            assert "https://" not in p.text


def test_colon_opens_roman_subpoints(ai_act: dict[str, ParsedDocument]) -> None:
    # Article 5(1)(h) ends with "objectives:", so the "(i)" after it is roman one.
    paragraph_1 = provision(ai_act["CHAPTER II"], "article:5").root.children[0]
    point_h = paragraph_1.children[7]

    assert labels(paragraph_1) == [f"({c})" for c in "abcdefgh"]
    assert labels(point_h) == ["(i)", "(ii)", "(iii)", None]
    assert {child.family for child in point_h.children[:3]} == {"roman"}
    # Text after the end of (iii) belongs to (h), not to (iii).
    assert (
        point_h.children[3].lines[0].startswith("Point (h) of the first subparagraph")
    )


def test_letter_i_continues_a_list(ai_act: dict[str, ParsedDocument]) -> None:
    # Article 7(2)(h) ends with ";", so the "(i)" after it is the ninth letter.
    paragraph_2 = provision(ai_act["CHAPTER III"], "article:7").root.children[1]

    assert labels(paragraph_2) == [f"({c})" for c in "abcdefghijk"]
    assert paragraph_2.children[8].family == "letter"
    assert labels(paragraph_2.children[10]) == ["(i)", "(ii)"]


def test_definitions(ai_act: dict[str, ParsedDocument]) -> None:
    article_3 = provision(ai_act["CHAPTER I"], "article:3")

    assert article_3.root.lines == [
        "For the purposes of this Regulation, the following definitions apply:"
    ]
    assert labels(article_3.root) == [f"({n})" for n in range(1, 69)]
    assert labels(article_3.root.children[44]) == ["(a)", "(b)"]


def test_text_without_item_end_stays_in_the_point(
    ai_act: dict[str, ParsedDocument],
) -> None:
    point_1 = ai_act["ANNEX III"].provisions[0].root.children[0]

    assert labels(point_1) == ["(a)", "(b)", "(c)"]
    assert point_1.children[0].lines[0] == "remote biometric identification systems."
    assert point_1.children[0].lines[1].startswith("This shall not include")


def test_point_text_is_not_an_annex_section(ai_act: dict[str, ParsedDocument]) -> None:
    article_49 = provision(ai_act["CHAPTER III"], "article:49")

    assert "(a) Section A, points 1 to 10, of Annex VIII" in article_49.text


def test_signature_is_dropped(ai_act: dict[str, ParsedDocument]) -> None:
    article_113 = ai_act["CHAPTER XIII"].provisions[-1]

    assert article_113.key == "article:113"
    assert "Done at Brussels" not in article_113.text
    assert article_113.text.endswith(
        "This Regulation shall be binding in its entirety and directly applicable in"
        " all Member States."
    )


def test_sub_numbered_items(ai_act: dict[str, ParsedDocument]) -> None:
    annex_vii = ai_act["ANNEX VII"].provisions[0]

    assert labels(annex_vii.root) == ["1.", "2.", "3.", "4.", "5."]
    assert annex_vii.root.children[0].lines[0] == "Introduction"
    assert labels(annex_vii.root.children[2]) == ["3.1.", "3.2.", "3.3.", "3.4."]
    assert labels(annex_vii.root.children[3]) == [f"4.{n}." for n in range(1, 8)]


def test_dashes(ai_act: dict[str, ParsedDocument]) -> None:
    annex_ii = ai_act["ANNEX II"].provisions[0]

    assert set(labels(annex_ii.root)) == {"—"}
    assert len(annex_ii.root.children) == 16
    assert annex_ii.root.children[0].lines == ["terrorism,"]


def test_annex_sections(ai_act: dict[str, ParsedDocument]) -> None:
    section_a = ai_act["ANNEX VIII"].provisions[0]

    assert section_a.label == "Annex VIII, Section A"
    assert section_a.title == (
        "Information to be submitted by providers of high-risk AI systems"
        " in accordance with Article 49(1)"
    )
    assert section_a.header.startswith(
        "Annex VIII — Information to be submitted upon the registration"
    )
    # The three heading forms: "Section A — Title", "Section A. Title", title below.
    assert ai_act["ANNEX I"].provisions[1].title == (
        "List of other Union harmonisation legislation"
    )
    assert ai_act["ANNEX XI"].provisions[0].title == (
        "Information to be provided by all providers of general-purpose AI models"
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "Line 1: expected 'CHAPTER <roman numeral>'"),
        ("Article 1\n\nSubject matter\n\nText.", "Line 1: expected 'CHAPTER"),
        (
            "CHAPTER I\n\nGENERAL\n\nSome text.",
            "Line 5: text outside of any article",
        ),
        (
            "CHAPTER I\n\nGENERAL\n\nArticle 1\n\nA\n\nText.\n\nArticle 1\n\nB\n\nText.",
            "Line 11: Article 1 appears twice",
        ),
        (
            "CHAPTER I\n\nGENERAL\n\nArticle 1\n\nArticle 2\n\nTitle\n\nText.",
            "Line 5: 'Article 1' has no title",
        ),
        ("CHAPTER I\n\nGENERAL\n\nArticle 1\n\nTitle", "Article 1 has no text"),
        (
            "CHAPTER I\n\nGENERAL\n\nArticle 1\n\nTitle\n\nText.\n\nANNEX I\n\nT",
            "Line 11: the file contains several documents",
        ),
        ("CHAPTER I\n\nGENERAL", "Chapter I contains no article"),
        ("ANNEX II\n\nList", "Annex II contains no text"),
    ],
)
def test_invalid_documents(text: str, message: str) -> None:
    with pytest.raises(ParseError, match=re.escape(message)):
        parse_document(text)
