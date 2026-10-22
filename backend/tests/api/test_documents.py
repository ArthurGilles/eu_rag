from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_session
from backend.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    # Without `with`, the lifespan does not run: these uploads are rejected before
    # any access to Postgres, Qdrant or Redis.
    app.dependency_overrides[get_session] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def upload(client: TestClient, content: bytes) -> httpx.Response:
    return client.post(
        "/api/documents", files={"file": ("document.md", content, "text/markdown")}
    )


def test_rejects_files_over_the_size_limit(client: TestClient) -> None:
    response = upload(client, b"CHAPTER V\n" + b"x" * 1_000_000)

    assert response.status_code == 413


def test_rejects_files_that_are_not_utf8(client: TestClient) -> None:
    response = upload(client, "CHAPTER V\n\nPRATIQUES INTERDITES é".encode("latin-1"))

    assert response.status_code == 422
    assert response.json()["detail"] == "The file is not valid UTF-8."


@pytest.mark.parametrize(
    "content", [b"Article 5\n\nProhibited AI practices", b"CHAPTER 5\n", b""]
)
def test_rejects_files_without_a_chapter_or_annex_heading(
    client: TestClient, content: bytes
) -> None:
    response = upload(client, content)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("The file must start with")
