"""Splits parsed provisions into chunks sized for embedding and retrieval.

A chunk never spans two provisions. A provision over the token budget is split into
groups of consecutive blocks of similar size; a block too large on its own is split
into groups of its children, each group repeating the block's own text (its chapeau).
"""

import math
from dataclasses import dataclass

from backend.rag.parsing import (
    Block,
    ParsedDocument,
    Provision,
    own_lines,
    render_block,
)


@dataclass
class Chunk:
    provision_key: str
    ref: str
    header: str
    text: str

    @property
    def embedding_text(self) -> str:
        """Text sent to both the dense and the BM25 embedding."""
        return f"{self.header}\n\n{self.text}"


# Lines of a chunk, labels of its split ancestors, labels of its top-level blocks.
_Piece = tuple[list[str], list[str], list[str]]


def estimate_tokens(text: str) -> int:
    """Approximate token count: about 4 characters per token for English legal text."""
    return math.ceil(len(text) / 4)


def chunk_document(document: ParsedDocument, max_tokens: int) -> list[Chunk]:
    return [
        chunk
        for provision in document.provisions
        for chunk in chunk_provision(provision, max_tokens)
    ]


def chunk_provision(provision: Provision, max_tokens: int) -> list[Chunk]:
    root = provision.root
    # Definitions are looked up one at a time: each one gets its own chunk.
    one_per_block = provision.is_article and provision.title == "Definitions"
    text = provision.text
    if not root.children or (not one_per_block and estimate_tokens(text) <= max_tokens):
        return [Chunk(provision.key, provision.label, provision.header, text)]
    pieces = _split(root.children, 0, own_lines(root, 0), [], max_tokens, one_per_block)
    return [
        Chunk(
            provision.key,
            _format_ref(provision, path, labels),
            provision.header,
            "\n".join(lines),
        )
        for lines, path, labels in pieces
    ]


def balanced_groups(sizes: list[int], budget: int) -> list[list[int]]:
    """Group consecutive items into about ceil(total / budget) groups of similar size.

    A group is closed when adding the next item would exceed the budget or move the
    group further from the target size, which is recomputed on what remains.
    """
    groups: list[list[int]] = []
    current: list[int] = []
    current_size = 0
    remaining = sum(sizes)
    target = remaining / max(1, math.ceil(remaining / budget))
    for index, size in enumerate(sizes):
        if current and (
            current_size + size > budget
            or abs(current_size + size - target) > abs(current_size - target)
        ):
            groups.append(current)
            remaining -= current_size
            target = remaining / max(1, math.ceil(remaining / budget))
            current, current_size = [], 0
        current.append(index)
        current_size += size
    groups.append(current)
    return groups


def _split(
    blocks: list[Block],
    depth: int,
    prefix: list[str],
    path: list[str],
    max_tokens: int,
    one_per_block: bool,
) -> list[_Piece]:
    rendered = [render_block(block, depth) for block in blocks]
    sizes = [estimate_tokens("\n".join(lines)) for lines in rendered]
    budget = max(1, max_tokens - estimate_tokens("\n".join(prefix)))
    if one_per_block:
        groups = [[index] for index in range(len(blocks))]
    else:
        groups = balanced_groups(sizes, budget)
    pieces: list[_Piece] = []
    for group in groups:
        block = blocks[group[0]]
        if len(group) == 1 and sizes[group[0]] > budget and block.children:
            pieces += _split(
                block.children,
                depth + 1 if block.label else depth,
                prefix + own_lines(block, depth),
                path + [block.label] if block.label else path,
                max_tokens,
                False,
            )
        else:
            lines = prefix + [line for index in group for line in rendered[index]]
            labels = [blocks[index].label for index in group if blocks[index].label]
            pieces.append((lines, path, labels))
    return pieces


def _format_ref(provision: Provision, path: list[str], labels: list[str]) -> str:
    """Citation of a chunk: "Article 5(1)(a)–(c)", "Annex III, point 4(a)–(e)"."""
    path = [_bare(label) for label in path if label != "—"]
    labels = [_bare(label) for label in labels if label != "—"]
    if not path and not labels:
        return provision.label
    if provision.is_article:
        return (
            provision.label
            + "".join(f"({label})" for label in path)
            + _range(labels, parentheses=True)
        )
    if labels and "." in labels[0]:
        path = []  # "4.1" already names its parent point
    if path:
        head = path[0] if path[0][0].isdigit() else f"({path[0]})"
        return (
            f"{provision.label}, point {head}"
            + "".join(f"({label})" for label in path[1:])
            + _range(labels, parentheses=True)
        )
    noun = "point" if labels[0] == labels[-1] else "points"
    parentheses = not labels[0][0].isdigit()
    return f"{provision.label}, {noun} {_range(labels, parentheses)}"


def _bare(label: str) -> str:
    return label.rstrip(".").strip("()")


def _range(labels: list[str], parentheses: bool) -> str:
    if not labels:
        return ""
    first, last = labels[0], labels[-1]
    if parentheses:
        first, last = f"({first})", f"({last})"
    return first if first == last else f"{first}–{last}"
