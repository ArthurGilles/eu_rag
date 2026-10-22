from types import SimpleNamespace

import pytest

from backend.rag.embedding import batch_texts, embed_texts


class FakeEmbeddings:
    """Stands for `Mistral.embeddings`: the vector of a text is [len(text)]."""

    def __init__(self, drop_last: bool = False) -> None:
        self.requests: list[list[str]] = []
        self.drop_last = drop_last

    def create(self, model: str, inputs: list[str]) -> SimpleNamespace:
        self.requests.append(inputs)
        data = [SimpleNamespace(embedding=[float(len(text))]) for text in inputs]
        return SimpleNamespace(data=data[:-1] if self.drop_last else data)


def test_batch_texts() -> None:
    texts = ["a" * 400, "b" * 400, "c" * 400]  # 100 estimated tokens each

    assert list(batch_texts(texts, 250)) == [texts[:2], texts[2:]]
    assert list(batch_texts(["x" * 4000], 250)) == [["x" * 4000]]
    assert list(batch_texts([], 250)) == []


def test_embed_texts_keeps_the_order_across_batches() -> None:
    client = SimpleNamespace(embeddings=FakeEmbeddings())
    texts = ["a" * 400, "b" * 800, "c" * 40]

    vectors = embed_texts(client, "mistral-embed", texts, 250)  # type: ignore[arg-type]

    assert vectors == [[400.0], [800.0], [40.0]]
    assert client.embeddings.requests == [texts[:1], texts[1:]]


def test_embed_texts_rejects_missing_embeddings() -> None:
    client = SimpleNamespace(embeddings=FakeEmbeddings(drop_last=True))

    with pytest.raises(RuntimeError, match="1 embeddings for 2 texts"):
        embed_texts(client, "mistral-embed", ["a", "b"], 250)  # type: ignore[arg-type]
