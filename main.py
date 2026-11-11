import io
import logging

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    MovieCache,
    MovieDataResponse,
    MovieProcessingReport,
    MovieStorage,
    MovieUploadInfo,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Movie API", version="3.0.0")
app.middleware("http")(log_requests)

storage = MovieStorage()
cache = MovieCache()


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "version": app.version}


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        logger.warning(f"Rejected unsupported file: {file.filename}")
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as error:
        logger.warning(f"Could not parse {file.filename}: {error}")
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {error}")

    if set(df.columns) != set(MOVIE_COLUMNS) or len(df.columns) != len(MOVIE_COLUMNS):
        logger.warning(f"Wrong columns in {file.filename}: {list(df.columns)}")
        raise HTTPException(status_code=400, detail=f"Columns must be exactly {MOVIE_COLUMNS}")
    if df.empty:
        logger.warning(f"No data rows in {file.filename}")
        raise HTTPException(status_code=400, detail="CSV has no data rows")

    df = df[MOVIE_COLUMNS]
    storage.save(df)
    cache.invalidate()
    logger.info(f"Uploaded movies: filename={file.filename}, rows={len(df)}")

    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
    }


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    cached = cache.get(limit)
    if cached is not None:
        logger.info(f"Cache hit: limit={limit}")
        return cached

    data = storage.select_columns(MOVIE_COLUMNS, limit=limit)
    total_rows = storage.count_movies()
    response = {"data": data, "total_rows": total_rows}

    cache.set(limit, response)
    logger.info(f"Retrieved movies: returned_rows={len(data)}")
    return response


@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1),
):
    try:
        results = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        logger.warning(f"Invalid search: {error}")
        raise HTTPException(status_code=400, detail=str(error))

    logger.info(
        f"Queried movies: columns={columns}, min_rating={min_rating}, "
        f"returned_rows={len(results)}"
    )
    return results


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    df = storage.get()
    if df.empty:
        logger.warning("Process requested but no movies are stored")
        raise HTTPException(status_code=400, detail="No movies stored")

    config_dict = config.model_dump()
    required_columns = config_dict["validation"]["required_columns"]
    numeric_columns = config_dict["validation"]["numeric_columns"]

    missing = [col for col in numeric_columns if col not in df.columns]
    if missing:
        logger.warning(f"Numeric columns not found: {missing}")
        raise HTTPException(status_code=400, detail=f"Numeric columns not found: {missing}")

    try:
        df_valid = validate_dataframe(df, required_columns, numeric_columns)
        validation_rows_removed = len(df) - len(df_valid)
        df_before = df_valid.copy()

        df_processed = process_data(df_valid, config_dict)
        report = create_cleaning_report(df_before, df_processed)
    except ValueError as error:
        logger.warning(f"Processing failed: {error}")
        raise HTTPException(status_code=400, detail=str(error))

    storage.save(df_processed)
    cache.invalidate()
    logger.info(
        f"Processed movies: validation_removed={validation_rows_removed}, "
        f"rows_before={len(df_before)}, rows_after={len(df_processed)}"
    )

    return {
        "validation_rows_removed": validation_rows_removed,
        "cleaning_report": report,
    }
