"""
Batch forecast runner.
Fits AutoARIMA for every SKU in the database and writes results to the
forecasts table.  Run once after load_m5.py, then re-run weekly.

Usage:
    python tools/run_baselines.py
    python tools/run_baselines.py --horizon 28 --category FOODS
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from tools.data_access import list_skus, get_con
from tools.forecasting import run_forecast

HORIZON = 28
STORE_ID = "CA_1"


def run(horizon: int = HORIZON, category: str = None) -> None:
    skus = list_skus(category)
    total = len(skus)
    print(f"Running forecasts: {total} SKUs, horizon={horizon} days, store={STORE_ID}")
    print("-" * 50)

    ok = 0
    failed = 0
    t_start = time.time()

    for i, sku in enumerate(skus, 1):
        t0 = time.time()
        result = run_forecast(sku, horizon_days=horizon, store_id=STORE_ID)
        elapsed = time.time() - t0

        if "error" in result:
            print(f"  [{i:3d}/{total}] SKIP  {sku}  ({result['error']})")
            failed += 1
        else:
            fc = result["forecast"]
            print(f"  [{i:3d}/{total}] OK    {sku}  "
                  f"next={fc[0]['point']:.1f}  "
                  f"model={result['model']}  "
                  f"{elapsed:.1f}s")
            ok += 1

    total_time = time.time() - t_start
    print("-" * 50)
    print(f"Done: {ok} OK, {failed} skipped, {total_time:.1f}s total")

    # Quick summary from DB
    con = get_con()
    n = con.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
    print(f"Forecasts table: {n:,} rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=HORIZON)
    parser.add_argument("--category", type=str, default=None,
                        help="FOODS, HOBBIES, or HOUSEHOLD")
    args = parser.parse_args()
    run(horizon=args.horizon, category=args.category)
