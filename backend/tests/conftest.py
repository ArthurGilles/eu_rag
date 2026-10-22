import re
from pathlib import Path

import pytest

from backend.rag.parsing import ParsedDocument, parse_document

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def chapter_v() -> str:
    return (FIXTURES / "chapter_v.md").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def annex_iv() -> str:
    return (FIXTURES / "annex_iv.md").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def ai_act_documents() -> dict[str, str]:
    """The full regulation cut into the 13 chapters and 13 annexes a user uploads."""
    text = (FIXTURES / "regulation_2024_1689.md").read_text(encoding="utf-8")
    starts = [
        match.start()
        for match in re.finditer(r"^(?:CHAPTER|ANNEX) [IVXLC]+$", text, re.MULTILINE)
    ]
    return {
        text[start:].split("\n", 1)[0]: text[start:end]
        for start, end in zip(starts, [*starts[1:], len(text)])
    }


@pytest.fixture(scope="session")
def ai_act(ai_act_documents: dict[str, str]) -> dict[str, ParsedDocument]:
    return {name: parse_document(text) for name, text in ai_act_documents.items()}
