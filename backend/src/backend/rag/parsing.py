"""Structural parser for AI Act chapters and annexes.

The files are EUR-Lex pages converted to markdown: the structure is not carried by
markdown syntax but by marker lines (`CHAPTER V`, `Article 53`, `1\\. text`, `(a)`
alone on its line, ...). The parser turns one chapter or one annex into provisions
(articles, annex sections or whole annexes), each holding a tree of blocks.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from backend.models.document import DocumentKind

HEADER_RE = re.compile(r"^(CHAPTER|ANNEX) ([IVXLC]+)$")
# Same heading, searched at the very start of a raw file (leading blank lines allowed).
HEADER_START_RE = re.compile(r"\s*(CHAPTER|ANNEX) ([IVXLC]+)[ \t]*$", re.MULTILINE)
SECTION_RE = re.compile(r"^SECTION (\d+)$")
ARTICLE_RE = re.compile(r"^Article (\d+)$")
# "Section A. Title", "Section A — Title", or "Section 1" with the title on the next line.
ANNEX_SECTION_RE = re.compile(r"^Section ([A-Z]|\d+)(?:\. (.+)| — (.+))?$")
NUMBERED_RE = re.compile(r"^(\d+(?:\.\d+)*)\.(?: (.*))?$")
POINT_RE = re.compile(r"^\(([a-z]+|\d+)\)$")
DASH_RE = re.compile(r"^[—–]$")
END_RE = re.compile(r"^(?:\* \* \*|Done at .*)$")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|])")

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_ROMAN_SYMBOLS = [
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
]

# A family of list markers and the item number within its list (None for dashes).
Interpretation = tuple[str, int | None]


class ParseError(ValueError):
    """The text does not follow the structure of an AI Act chapter or annex."""


@dataclass
class Block:
    """A paragraph, point or sub-point: its own text, then its nested blocks.

    `label` is None for the root of a provision and for unnumbered subparagraphs.
    """

    label: str | None = None
    family: str | None = None
    ordinal: int | None = None
    lines: list[str] = field(default_factory=list)
    children: list["Block"] = field(default_factory=list)


@dataclass
class Provision:
    """A citable unit: an article, an annex section, or a whole annex."""

    key: str
    label: str
    title: str
    context: list[str]
    is_article: bool
    root: Block = field(default_factory=Block)

    @property
    def header(self) -> str:
        return " › ".join([*self.context, f"{self.label} — {self.title}"])

    @property
    def text(self) -> str:
        return "\n".join(render_block(self.root))


@dataclass
class ParsedDocument:
    kind: DocumentKind
    number: int
    title: str
    provisions: list[Provision]

    @property
    def label(self) -> str:
        return f"{self.kind.title()} {int_to_roman(self.number)}"

    @property
    def doc_key(self) -> str:
        return f"{self.kind}:{int_to_roman(self.number)}"


def roman_to_int(numeral: str) -> int:
    total = 0
    for current, following in zip(numeral, [*numeral[1:], None]):
        value = _ROMAN_VALUES[current]
        total += -value if following and _ROMAN_VALUES[following] > value else value
    return total


def int_to_roman(number: int) -> str:
    numeral = ""
    for value, symbol in _ROMAN_SYMBOLS:
        count, number = divmod(number, value)
        numeral += symbol * count
    return numeral


def read_header(text: str) -> tuple[DocumentKind, int] | None:
    """Kind and number of the document if the text starts with its CHAPTER/ANNEX line."""
    match = HEADER_START_RE.match(text)
    if match is None or int_to_roman(roman_to_int(match[2])) != match[2]:
        return None
    return DocumentKind(match[1].lower()), roman_to_int(match[2])


def render_block(block: Block, depth: int = 0) -> list[str]:
    """Render a block and its descendants as indented lines, labels included."""
    lines = own_lines(block, depth)
    child_depth = depth + 1 if block.label else depth
    for child in block.children:
        lines += render_block(child, child_depth)
    return lines


def own_lines(block: Block, depth: int) -> list[str]:
    """Render the block's own text (its chapeau when it has children)."""
    indent = "  " * depth
    if not block.lines:
        return [f"{indent}{block.label}"] if block.label else []
    first, *rest = block.lines
    head = f"{block.label} {first}" if block.label else first
    return [f"{indent}{head}", *(f"{indent}{line}" for line in rest)]


def parse_document(text: str) -> ParsedDocument:
    return _Parser(text).parse()


def _normalize(raw: str) -> str:
    line = LINK_RE.sub(r"\1", raw)
    line = ESCAPE_RE.sub(r"\1", line)
    return " ".join(line.split())


def _point_interpretations(label: str) -> list[Interpretation]:
    """Possible readings of a "(x)" marker: "(i)" is both the 9th letter and roman one."""
    if label.isdigit():
        return [("paren", int(label))]
    interpretations: list[Interpretation] = []
    if len(label) == 1:
        interpretations.append(("letter", ord(label) - ord("a") + 1))
    if re.fullmatch(r"[ivx]+", label):
        value = roman_to_int(label.upper())
        if int_to_roman(value).lower() == label:
            interpretations.append(("roman", value))
    return interpretations or [("letter", None)]


def _last_labeled_child(block: Block) -> Block | None:
    return next((child for child in reversed(block.children) if child.label), None)


class _Parser:
    def __init__(self, text: str) -> None:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self._lines: Iterator[tuple[int, str]] = iter(enumerate(lines, start=1))
        self._provisions: list[Provision] = []
        self._article_numbers: set[int] = set()
        # Open blocks, from the provision root to the block receiving text.
        self._stack: list[Block] = []
        self._last_text = ""

    def parse(self) -> ParsedDocument:
        lineno, line = self._next_content_line() or (1, "")
        match = HEADER_RE.fullmatch(line)
        if match is None or int_to_roman(roman_to_int(match[2])) != match[2]:
            raise ParseError(
                f"Line {lineno}: expected 'CHAPTER <roman numeral>' or "
                f"'ANNEX <roman numeral>', got '{line}'."
            )
        kind = DocumentKind(match[1].lower())
        numeral = match[2]
        title = self._title(lineno, f"{kind.title()} {numeral}")
        if kind is DocumentKind.chapter:
            self._parse_chapter(numeral, title)
        else:
            self._parse_annex(numeral, title)
        for provision in self._provisions:
            if not provision.root.lines and not provision.root.children:
                raise ParseError(f"{provision.label} has no text.")
        return ParsedDocument(kind, roman_to_int(numeral), title, self._provisions)

    def _parse_chapter(self, numeral: str, title: str) -> None:
        chapter = f"Chapter {numeral} — {title}"
        section: str | None = None
        for lineno, line in self._body():
            if match := SECTION_RE.fullmatch(line):
                section = f"Section {match[1]} — {self._title(lineno, line)}"
                self._stack = []
            elif match := ARTICLE_RE.fullmatch(line):
                number = int(match[1])
                if number in self._article_numbers:
                    raise ParseError(f"Line {lineno}: Article {number} appears twice.")
                self._article_numbers.add(number)
                self._start(
                    Provision(
                        key=f"article:{number}",
                        label=f"Article {number}",
                        title=self._title(lineno, line),
                        context=[chapter] if section is None else [chapter, section],
                        is_article=True,
                    )
                )
            elif not self._stack:
                raise ParseError(
                    f"Line {lineno}: text outside of any article: '{line}'."
                )
            else:
                self._add_content(line)
        if not self._provisions:
            raise ParseError(f"Chapter {numeral} contains no article.")

    def _parse_annex(self, numeral: str, title: str) -> None:
        annex = f"Annex {numeral}"
        for lineno, line in self._body():
            if match := ANNEX_SECTION_RE.fullmatch(line):
                name = match[1]
                key = f"annex:{numeral}:{name}"
                if any(provision.key == key for provision in self._provisions):
                    raise ParseError(f"Line {lineno}: Section {name} appears twice.")
                self._start(
                    Provision(
                        key=key,
                        label=f"{annex}, Section {name}",
                        title=match[2] or match[3] or self._title(lineno, line),
                        context=[f"{annex} — {title}"],
                        is_article=False,
                    )
                )
                continue
            if not self._stack:
                # Text before any section: the annex itself is the provision.
                self._start(
                    Provision(
                        key=f"annex:{numeral}",
                        label=annex,
                        title=title,
                        context=[],
                        is_article=False,
                    )
                )
            self._add_content(line)
        if not self._provisions:
            raise ParseError(f"{annex} contains no text.")

    def _body(self) -> Iterator[tuple[int, str]]:
        """Yield the normalized content lines, handling end markers and item ends."""
        for lineno, raw in self._lines:
            if raw and not raw.strip():
                # A whitespace-only line ends the current list item: it is what remains
                # of the HTML table cells EUR-Lex uses for points.
                if len(self._stack) > 1:
                    self._stack.pop()
                continue
            line = _normalize(raw)
            if not line:
                continue
            if END_RE.fullmatch(line):
                return
            if HEADER_RE.fullmatch(line):
                raise ParseError(
                    f"Line {lineno}: the file contains several documents ('{line}'); "
                    "upload chapters and annexes one at a time."
                )
            yield lineno, line

    def _next_content_line(self) -> tuple[int, str] | None:
        for lineno, raw in self._lines:
            if line := _normalize(raw):
                return lineno, line
        return None

    def _title(self, lineno: int, heading: str) -> str:
        """The title of a heading is the next non-empty line."""
        found = self._next_content_line()
        if found is None or any(
            regex.fullmatch(found[1])
            for regex in (HEADER_RE, SECTION_RE, ARTICLE_RE, NUMBERED_RE, POINT_RE)
        ):
            raise ParseError(f"Line {lineno}: '{heading}' has no title.")
        return found[1]

    def _start(self, provision: Provision) -> None:
        self._provisions.append(provision)
        self._stack = [provision.root]
        self._last_text = ""

    def _add_content(self, line: str) -> None:
        if match := NUMBERED_RE.fullmatch(line):
            number = match[1]
            family = f"number{number.count('.') + 1}"
            self._open(f"{number}.", [(family, int(number.rsplit(".", 1)[-1]))])
            if match[2]:
                self._add_text(match[2])
        elif match := POINT_RE.fullmatch(line):
            self._open(f"({match[1]})", _point_interpretations(match[1]))
        elif DASH_RE.fullmatch(line):
            self._open("—", [("dash", None)])
        else:
            self._add_text(line)

    def _add_text(self, line: str) -> None:
        top = self._stack[-1]
        if top.children:
            # Text after nested items is a new subparagraph of the same parent.
            subparagraph = Block()
            top.children.append(subparagraph)
            self._stack.append(subparagraph)
            top = subparagraph
        top.lines.append(line)
        self._last_text = line

    def _open(self, label: str, interpretations: list[Interpretation]) -> None:
        index, (family, ordinal) = self._place(interpretations)
        del self._stack[index + 1 :]
        block = Block(label=label, family=family, ordinal=ordinal)
        self._stack[-1].children.append(block)
        self._stack.append(block)

    def _place(
        self, interpretations: list[Interpretation]
    ) -> tuple[int, Interpretation]:
        """Index of the open block that receives the new item, and its interpretation."""
        top = len(self._stack) - 1
        # A text ending with a colon announces a nested list, which starts at item 1.
        if self._last_text.endswith(":"):
            for family, ordinal in interpretations:
                if ordinal in (1, None):
                    return top, (family, ordinal)
        # Otherwise the item continues the deepest open list of its family, preferring
        # the reading whose previous item is its predecessor: (h) -> (i), (iv) -> (v).
        for consecutive in (True, False):
            for index in range(top, -1, -1):
                last = _last_labeled_child(self._stack[index])
                if last is None:
                    continue
                for family, ordinal in interpretations:
                    if last.family != family:
                        continue
                    if (
                        not consecutive
                        or ordinal is None
                        or last.ordinal is None
                        or last.ordinal == ordinal - 1
                    ):
                        return index, (family, ordinal)
        # A new list nested in the current block.
        first = next((i for i in interpretations if i[1] == 1), interpretations[0])
        return top, first
