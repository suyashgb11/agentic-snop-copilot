"""
Data quality checks and zero-demand handling.
Call after load_m5.load() to annotate the sales table.
"""

import os
import duckdb
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("DUCKDB_PATH", "data/snop.duckdb"))


def detect_stockouts(con: duckdb.DuckDBPyConnection, min_run: int = 3) -> pd.DataFrame:
    """
    Flag zero-demand runs that look like stockouts (sustained zeros ≥ min_run days)
    vs genuine zero-demand days (isolated zeros).
    Returns a DataFrame of (sku_id, store_id, start_date, end_date, run_length).
    """
    query = f"""
    WITH zeros AS (
        SELECT
            sku_id,
            store_id,
            date,
            units,
            SUM(CASE WHEN units > 0 THEN 1 ELSE 0 END)
                OVER (PARTITION BY sku_id, store_id ORDER BY date) AS grp
        FROM sales
    ),
    runs AS (
        SELECT
            sku_id,
            store_id,
            MIN(date) AS start_date,
            MAX(date) AS end_date,
            COUNT(*) AS run_length
        FROM zeros
        WHERE units = 0
        GROUP BY sku_id, store_id, grp
    )
    SELECT * FROM runs
    WHERE run_length >= {min_run}
    ORDER BY run_length DESC
    """
    return con.execute(query).df()


def report_quality(con: duckdb.DuckDBPyConnection) -> None:
    """Print a data quality summary to stdout."""
    stats = con.execute("""
        SELECT
            COUNT(DISTINCT sku_id) AS skus,
            COUNT(DISTINCT store_id) AS stores,
            COUNT(*) AS total_rows,
            MIN(date) AS earliest,
            MAX(date) AS latest,
            ROUND(AVG(units), 2) AS avg_units,
            SUM(CASE WHEN units = 0 THEN 1 ELSE 0 END) AS zero_rows,
            ROUND(100.0 * SUM(CASE WHEN units = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_zero
        FROM sales
    """).fetchone()

    print("=== Data Quality Report ===")
    print(f"  SKUs:        {stats[0]}")
    print(f"  Stores:      {stats[1]}")
    print(f"  Total rows:  {stats[2]:,}")
    print(f"  Date range:  {stats[3]} to {stats[4]}")
    print(f"  Avg units:   {stats[5]}")
    print(f"  Zero rows:   {stats[6]:,} ({stats[7]}%)")

    stockouts = detect_stockouts(con)
    print(f"  Stockout runs (>=3 days): {len(stockouts)}")
    if not stockouts.empty:
        top = stockouts.head(5)
        for _, row in top.iterrows():
            print(f"    {row['sku_id']} {row['store_id']}: "
                  f"{row['start_date']} to {row['end_date']} ({row['run_length']} days)")


def run() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    report_quality(con)
    con.close()


if __name__ == "__main__":
    run()
