# data_processor.py
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def remove_duplicates(df):
    """Remove duplicate rows."""
    rows_before = len(df)
    df = df.drop_duplicates()
    logger.debug(f"remove_duplicates: {rows_before} -> {len(df)} rows")
    return df


def handle_missing(df, axis="rows"):
    """Drop rows or columns containing missing values."""
    if axis == "rows":
        rows_before = len(df)
        df = df.dropna(axis=0)
        logger.debug(f"handle_missing: {rows_before} -> {len(df)} rows")
    elif axis == "columns":
        cols_before = len(df.columns)
        df = df.dropna(axis=1)
        logger.debug(f"handle_missing: {cols_before} -> {len(df.columns)} columns")
    else:
        logger.error(f"Unsupported axis: {axis}")
        raise ValueError(f"Unsupported axis: {axis}")
    return df


def remove_outliers(df, columns, method, threshold):
    """Remove outliers from the specified numeric columns."""
    if method not in ("iqr", "zscore"):
        logger.error(f"Unsupported outlier method: {method}")
        raise ValueError(f"Unsupported outlier method: {method}")

    for col in columns:
        if col not in df.columns:
            logger.warning(f"Column not found: {col}")
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            logger.warning(f"Column is not numeric: {col}")
            continue

        if method == "iqr":
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
            keep = df[col].between(lower, upper)
        else:  # zscore
            mean = df[col].mean()
            std = df[col].std()
            if std == 0 or pd.isna(std):
                # All values identical (or too few rows): nothing is an outlier
                keep = pd.Series(True, index=df.index)
            else:
                z = (df[col] - mean) / std
                keep = z.abs() <= threshold

        # Missing values are not outliers; handle_missing() deals with those
        keep = keep | df[col].isna()

        rows_before = len(df)
        df = df[keep]
        logger.debug(
            f"{col}: method={method}, threshold={threshold}, "
            f"removed={rows_before - len(df)}"
        )
    return df


def process_data(df, config):
    """Apply the processing steps enabled in the configuration."""
    processing = config.get("processing", {})

    # 1. Remove duplicates
    if processing.get("remove_duplicates", False):
        df = remove_duplicates(df)

    # 2. Handle missing values
    missing = processing.get("missing", {})
    if missing.get("enabled", False):
        df = handle_missing(df, axis=missing.get("axis", "rows"))

    # 3. Remove outliers
    outliers = processing.get("outliers", {})
    if outliers.get("enabled", False):
        df = remove_outliers(
            df,
            columns=outliers.get("columns", []),
            method=outliers.get("method"),
            threshold=outliers.get("threshold"),
        )

    return df


def create_cleaning_report(df_before, df_after):
    """Return a dictionary summarizing the cleaning results."""
    rows_before, columns_before = df_before.shape
    rows_after, columns_after = df_after.shape
    return {
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_removed": rows_before - rows_after,
        "columns_before": columns_before,
        "columns_after": columns_after,
        "columns_removed": columns_before - columns_after,
    }
