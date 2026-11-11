# MP3 Movie API

This FastAPI application stores a movie collection in SQLite, filters it with SQL, cleans it with the MP1 data pipeline, and caches repeated retrievals with fakeredis. `src/database.py` creates SQLite connections and the `movies` table, and `src/storage.py` (`MovieStorage`) saves, retrieves, counts, and filters movies using SQL. Each successful `POST /upload` replaces the stored collection in one transaction, so the data persists after a server restart. `POST /movies/process` loads the stored movies, validates and cleans them with the `data_pipeline` modules, and saves the processed result back to SQLite. `src/cache.py` (`MovieCache`) caches `GET /movies` responses by `limit` for 90 seconds, so repeated requests skip the database. After every successful upload or processing step, the cache is invalidated so clients never receive outdated results. `GET /movies/search` is not cached and filters by minimum rating using SQL.

## Run the API

```bash
python -m uvicorn main:app --reload
```

Open http://127.0.0.1:8000/docs

## Run the tests

```bash
python -m pytest tests -v
```

## Sample processing request

After uploading `fixtures/sample_movies.csv`, send this to `POST /movies/process`:

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {"enabled": true, "columns": ["rating"], "method": "iqr", "threshold": 1.5}
  }
}
```

Expected result:

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```
