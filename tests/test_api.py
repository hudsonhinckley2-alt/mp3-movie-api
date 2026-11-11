import pandas as pd
import pytest

from src import MovieStorage
import main

MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]


def test_movies_persist(client, test_storage, uploaded_movies):
    other = MovieStorage(test_storage.db_path)
    df = other.get()

    assert len(df) == 20
    assert other.count_movies() == 20
    assert list(df.columns) == MOVIE_COLUMNS

    original_titles = pd.read_csv("fixtures/sample_movies.csv")["title"].tolist()
    assert df["title"].tolist() == original_titles

    storage_ids = [row["id"] for row in other.select_columns(["title"], limit=100)]
    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200
    api_ids = [row["id"] for row in response.json()["data"]]

    assert storage_ids == list(range(1, 21))
    assert api_ids == list(range(1, 21))


def test_cache_and_processing(client, uploaded_movies, processing_body):
    # 1: first retrievals get cached
    r100 = client.get("/movies", params={"limit": 100})
    assert r100.status_code == 200
    assert main.cache.get(100) == r100.json()

    r1 = client.get("/movies", params={"limit": 1})
    assert r1.status_code == 200
    assert main.cache.get(1) == r1.json()

    # 2: repeat returns the same response
    again = client.get("/movies", params={"limit": 100})
    assert again.status_code == 200
    assert again.json() == r100.json()

    # 3: processing removes 4 rows and clears the cache
    processed = client.post("/movies/process", json=processing_body)
    assert processed.status_code == 200
    body = processed.json()
    assert body["validation_rows_removed"] == 0
    report = body["cleaning_report"]
    assert report["rows_before"] == 20
    assert report["rows_after"] == 16
    assert report["rows_removed"] == 4
    assert main.cache.get(100) is None
    assert main.cache.get(1) is None

    # 4: new retrieval shows the 16 processed rows and is cached
    new = client.get("/movies", params={"limit": 100})
    assert new.status_code == 200
    data = new.json()
    assert data["total_rows"] == 16
    expected_titles = [f"Movie {letter}" for letter in "ABCDEFGHIJKLMNOP"]
    assert [m["title"] for m in data["data"]] == expected_titles
    assert [m["id"] for m in data["data"]] == list(range(1, 17))
    assert main.cache.get(100) == data


def test_cache_hit_skips_database(client, uploaded_movies, monkeypatch):
    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200

    def fail_if_called(*args, **kwargs):
        pytest.fail("Database was called on a cache hit")

    monkeypatch.setattr(main.storage, "select_columns", fail_if_called)
    monkeypatch.setattr(main.storage, "count_movies", fail_if_called)

    second = client.get("/movies", params={"limit": 100})
    assert second.status_code == 200
    assert second.json() == first.json()
