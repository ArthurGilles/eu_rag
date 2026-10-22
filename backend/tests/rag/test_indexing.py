from backend.rag.indexing import point_id


def test_point_ids_are_deterministic_per_version() -> None:
    # A retried task overwrites its own points; another version gets other points.
    assert point_id("chapter:V", 1, 0) == point_id("chapter:V", 1, 0)
    assert point_id("chapter:V", 1, 0) != point_id("chapter:V", 2, 0)
    assert point_id("chapter:V", 1, 0) != point_id("annex:V", 1, 0)
